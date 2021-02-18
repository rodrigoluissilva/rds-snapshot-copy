import os
import uuid
import boto3
import logging
import botocore
import datetime

logging.basicConfig(format='%(asctime)-15s [%(name)s] [%(levelname)s] '
                           '(%(request_id)s) %(aws_region)s %(message)s')
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

ec2 = boto3.client('ec2')

default_tag = os.environ.get('custom_tag', 'scheduler:rds-snapshot-copy')
default_retention_days = int(os.environ.get('default_retention_days', 7))
custom_aws_regions = os.environ.get('custom_aws_regions', None)

if custom_aws_regions is not None:
    aws_regions = [region.strip().lower() for region in custom_aws_regions.split(',')]
else:
    aws_regions = [region['RegionName'] for region in ec2.describe_regions()['Regions']]


def lambda_handler(event=None, context=None):

    if context is None:
        request_id = uuid.uuid4()
    else:
        request_id = context.aws_request_id

    for aws_region in aws_regions:

        log_extra = {'request_id': request_id, 'aws_region': aws_region}
        logger.debug('Entering aws region', extra=log_extra)

        rds = boto3.client('rds', region_name=aws_region)

        """
        Copy automated snapshot to a different aws region
        """
        paginator = rds.get_paginator('describe_db_snapshots')
        snapshot_pages = paginator.paginate(SnapshotType='automated')

        for snapshots in snapshot_pages:

            for snapshot in snapshots['DBSnapshots']:

                snapshot_tagged = False
                source_identifier = snapshot['DBSnapshotIdentifier']
                target_identifier = source_identifier.split(':')[1]

                for tag in rds.list_tags_for_resource(
                        ResourceName=snapshot['DBSnapshotArn']
                        )['TagList']:
                    if tag['Key'] == default_tag:
                        logger.debug("Value for tag ({}) in the snapshot ({})"
                                     "is ({})".format(default_tag, source_identifier,
                                                      tag['Value']),
                                     extra=log_extra)
                        snapshot_tagged = True
                        try:
                            config = {
                                k.lower().strip(): v.lower().strip()
                                for k, v in [option.split('=')
                                             for option in tag['Value'].split(':')]
                                }
                        except ValueError:
                            config = {'enable': False,
                                      'parse_error': tag['Value']}

                if snapshot_tagged is False:
                    logger.debug("Ignoring snapshot ({}) for copy, "
                                 "tag ({}) not found".format(source_identifier,
                                                             default_tag),
                                 extra=log_extra)
                    continue

                if config.get('parse_error', False) is False and config.get('copyto', None) is None:
                    logger.warning('Snapshot ({}) has no destination set'.format(source_identifier),
                                   extra=log_extra)
                    continue

                config['enable'] = True \
                    if config.get('enable') in ('yes', 'true') \
                    else False
                config['copytags'] = True \
                    if config.get('copytags') in ('yes', 'true') \
                    else False
                config['retention'] = int(config.get('retention')) \
                    if config.get('retention', '').isdigit() \
                    else default_retention_days
                config['copyto'] = [dest.lower().strip()
                                    for dest in config.get('copyto', '').split('/')]

                logger.debug("Using the config ({}) for "
                             "snapshot ({})".format(config,
                                                    source_identifier),
                             extra=log_extra)

                if config.get('enable'):
                    for destination in config['copyto']:
                        if destination not in aws_regions:
                            continue

                        try:
                            rds_target = boto3.client('rds', region_name=destination)
                            response = rds_target.copy_db_snapshot(
                                    SourceDBSnapshotIdentifier=snapshot['DBSnapshotArn'],
                                    TargetDBSnapshotIdentifier=target_identifier,
                                    CopyTags=True,
                                    SourceRegion=aws_region
                                    )
                            expire_date = str(datetime.date.today()
                                              + datetime.timedelta(days=config['retention']))
                            dest_region = [dest
                                           for dest in config['copyto']
                                           if dest not in aws_regions]
                            if len(dest_region) == 0:
                                rds.remove_tags_from_resource(
                                        ResourceName=snapshot['DBSnapshotArn'],
                                        TagKeys=[default_tag]
                                        )
                            new_tags = [{'Key': default_tag,
                                         'Value': expire_date}]
                            rds_target.add_tags_to_resource(
                                    ResourceName=response['DBSnapshot']['DBSnapshotArn'],
                                    Tags=new_tags
                                    )
                            logger.info("Snapshost ({}) copied to ({}) "
                                        "as ({})".format(source_identifier, destination,
                                                         target_identifier),
                                        extra=log_extra)
                        except botocore.exceptions.ClientError as e:
                            if e.response['Error']['Code'] == 'DBSnapshotAlreadyExists':
                                logger.info('Snapshot with the identifier {} '
                                            'already exists'.format(target_identifier),
                                            extra=log_extra)
                            elif e.response['Error']['Code'] == 'SnapshotQuotaExceeded':
                                logger.info('Skipping snapshot ({}). Cannot copy more than 5 '
                                            'snapshots across regions'.format(source_identifier),
                                            extra=log_extra)
                            else:
                                logger.error("Snapshost ({}): {}".format(source_identifier, e), 
                                             extra=log_extra)
                            continue
                else:
                    if config.get('parse_error', False):
                        logger.error('Parser error for snapshot ({}) '
                                     '[{}]'.format(source_identifier,
                                                   config.get('parse_error')),
                                     extra=log_extra)
                    else:
                        logger.debug('Backup Disabled for snapshot ({})'.format(source_identifier),
                                     extra=log_extra)

        """
        Remove expired snapshots
        """
        snapshot_pages = paginator.paginate(SnapshotType='manual')

        for snapshots in snapshot_pages:
            for snapshot in snapshots['DBSnapshots']:

                snapshot_tagged = False
                snapshot_id = snapshot['DBSnapshotIdentifier']

                for tag in rds.list_tags_for_resource(
                        ResourceName=snapshot['DBSnapshotArn']
                        )['TagList']:
                    if tag['Key'] == default_tag:
                        try:
                            expire_date = datetime.datetime.strptime(tag['Value'], '%Y-%m-%d').date()
                            snapshot_tagged = True
                        except Exception:
                            logger.error('Error parsing tag for snapshot ({}) '
                                     'tag value ({})'.format(snapshot_id,
                                                              tag['Value']),
                                        extra=log_extra)

                if snapshot_tagged and expire_date <= datetime.date.today():
                    try:
                        rds.delete_db_snapshot(DBSnapshotIdentifier=snapshot_id)
                        logger.warning('Removing snapshot ({}) '
                                       'expired on ({})'.format(snapshot_id,
                                                                expire_date),
                                       extra=log_extra)
                    except Exception:
                        logger.error('Error removing snapshot ({}) '
                                     'expired on ({})'.format(snapshot_id,
                                                              expire_date),
                                     extra=log_extra)

                elif snapshot_tagged:
                    logger.debug("Keeping snapshot ({}) "
                                 "until ({})".format(snapshot_id,
                                                     expire_date),
                                 extra=log_extra)
                else:
                    logger.debug("Ignoring snapshot ({}) for deletion, "
                                 "tag ({}) not found".format(snapshot_id,
                                                             default_tag),
                                 extra=log_extra)


if __name__ == '__main__':
    lambda_handler()
