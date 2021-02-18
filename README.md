
# rds-snapshot-copy

> AWS Lambda function written in Python to manage RDS Snapshots Copy

## Description

The Lambda function "*rds-snapshot-copy*" copy RDS snapshot to a different aws region as backup strategy.

## Features

 - Automatic snapshot deletion on expiration date
 - Automatic cross region snapshot copy
 - Work on all or pre-defined aws region

## Lambda Creation

Follow these steps to get your lambda function running.

### IAM Role

Add this IAM role. It will be attached to your lambda function.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

You can add via command line

```
aws iam create-role --role-name lambda-rds-snapshot-copy --path /service-role/ --description "Automatic RDS Snapshot cross-region copy" --assume-role-policy-document https://raw.githubusercontent.com/rodrigoluissilva/rds-snapshot-copy/master/lambda-role.json
```

### IAM Policy

Now you have to attach this policy to allow a few actions to be performed.

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "logs:CreateLogStream",
                "logs:CreateLogGroup",
                "logs:PutLogEvents"
            ],
            "Resource": "arn:aws:logs:*:*:log-group:/aws/lambda/*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "ec2:DescribeRegions",
                "rds:DescribeDBSnapshots",
                "rds:CopyDBSnapshot",
                "rds:DeleteDBSnapshot",
                "rds:ListTagsForResource",
                "rds:AddTagsToResource",
                "rds:RemoveTagsFromResource"
            ],
            "Resource": "*"
        }
    ]
}
```

This can be done via command line

```
aws iam put-role-policy --role-name lambda-rds-snapshot-copy --policy-name rds-snapshot-copy --policy-document https://raw.githubusercontent.com/rodrigoluissilva/rds-snapshot-copy/master/lambda-policy.json
```

### Lambda Function

#### Console

Add a new Lambda function using these options.

**Name**: rds-snapshot-copy
**Runtime**: Python 3.6
**Existing Role**: service-role/lambda-rds-snapshot-copy

![Lambda Create Function Sample Screen](https://image.prntscr.com/image/7QQ3S4K7TsuuaJPqhObihw.png)

Change the **timeout to 5 minutes** and add some useful description.

![Lambda Function Basic Settings Sample Screen](https://image.prntscr.com/image/wXq8S9bDT729gKk5nkBBvg.png)

Paste the code from the file *rds-snapshot-copy.py* in the Lambda Function Code area.

You can set a test event using the "**Scheduled Event**" template.

#### Command Line

Download the file *rds-snapshot-copy.py*.
Rename it to *lambda_function.py*.
Compress it as a *zip file*.

Get the IAM Role ARN using this command.

```
aws iam get-role --role-name lambda-rds-snapshot-copy
```

Replace the ARN by the one from the previous command.

```
aws lambda create-function --region us-east-1 --function-name rds-snapshot-copy --description "Automatic RDS Snapshot cross-region copy" --zip-file fileb://lambda_function.zip --handler lambda_function.lambda_handler --runtime python3.6 --timeout 300 --role arn:aws:iam::XXXXXXXXXXXX:role/lambda-rds-snapshot-copy
```

## Schedule

This lambda function is triggered by one CloudWatch Event Rule.
Run this command to set it to run at 3 am everyday.

```
aws events put-rule --name rds-snapshot-copy --schedule-expression "cron(0 3 * * ? *)" --description "Trigger the rds-snapshot-copy function"
```

Add permission to CloudWatch invoke the Lambda Function.
Use the ARN from the previous command.

```
aws lambda add-permission --function-name rds-snapshot-copy --statement-id rds-snapshot-copy --action lambda:InvokeFunction --principal events.amazonaws.com --source-arn arn:aws:events:us-east-1:XXXXXXXXXXXX:rule/rds-snapshot-copy
```

Get the Lambda Function ARN with this command.

```
aws lambda get-function-configuration --function-name rds-snapshot-copy
```

Replace this ARN by the one from the previous command.

```
aws events put-targets --rule rds-snapshot-copy --targets "Id"="1","Arn"="arn:aws:lambda:us-east-1:XXXXXXXXXXXX:function:rds-snapshot-copy"
```

## Volume Configuration

The default tag is "*scheduler:rds-snapshot-copy*"

To enable the backup, add this tag and the value following the specific pattern as described bellow.

**Key**: scheduler:rds-snapshot-copy

**Value**: Enable=Yes : Retention=16 : CopyTags=Yes : CopyTo=us-west-1 / us-west-2

The minimum setting for a daily snapshot creation is

**Key**: scheduler:rds-snapshot-copy

**Value**: Enable=Yes : CopyTo=us-west-1

### Parameters details

| Parameter | Description |Values|
|--|--|--|
| **Enable** |Enable or Disable snapshot copy.<br>You have to set the CopyTo as well.| **Yes** – Enable<br>**No** – Disable (**default**) |
|**Retention**|The number of days to keep the snapshot.|1, 2, 3, 4, 5, ...<br> (**default**: 7)|
|**CopyTags**|Copy snapshot tags.|**Yes** – Copy all tags<br>**No** – Don’t copy tags  (**default**)|
|**CopyTo**|Make a copy of this snapshot to the defined region.<br>Could be one or more values.<br><br>CopyTo=us-east-2<br>CopyTo=us-east-2 / us-west-1<br>|ap-south-1, eu-west-3, eu-west-2, eu-west-1, ap-northeast-2, ap-northeast-1, sa-east-1, ca-central-1, ap-southeast-1, ap-southeast-2, eu-central-1, us-east-1, us-east-2, us-west-1, us-west-2<br><br>**Default**: None|

## Lambda Environment Variables

You can set a few environment variables to control how the Lambda Function will behave.

Key|Description|Value
-|-|-
**custom_aws_regions**|A list of AWS Regions to be used during the execution time.<br>Could be one or more regions.<br><br>custom_aws_regions=us-east-1, us-east-2, us-west-1|Any valid AWS region.
**custom_tag**|Define the tag name to be used.|Any valid tag name.
**default_retention_days**|The default retention period in days.|Any valid number of days.