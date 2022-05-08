# Telemetry mapping

This project contains source code and supporting files for a telemetry mapping of SQS queue `sensor-fleet` to kinesis stream `events`. You can deploy with the SAM CLI. It includes the following files and folders.

- `submissions_to_events` - Code for the application's Lambda function.
- `events` - Invocation events that you can use to invoke the function.
- `template.yaml` - A template that defines the application's AWS resources.

## Development Overview
We have used AWS serverless functions to make this mapping. The function can read continuously from SQS queue map this data to
Kinesis event stream.

```python
def lambda_handler(event, context):

	kinesis_records_all = {}

	# all successfully mapped submissions
	kinesis_records_all['valid'] = []

	# list of parsed but failed submissions
	kinesis_records_all['failed'] = []

	for message in event['Messages']:
		kinesis_records_all = add_message(message, kinesis_records_all)
        	
    #pushing records retrieved from submissions source to respective streams & drop malformed records.
	batchItemFailures = push_to_kinesis(kinesis_records_all)

	return batchItemFailures
```
`lambda_handler` is the main function the receive the request. We record all successfully processed records to `valid` list. `failed` 
list will contain events that failed to be submitted to Kinesis. At the end we return the list of valid but failed submission. This is indicate to Lambda hanler to keep those messages in the queue for further retry.

```python

def map_event(message, extra):
	'''
	Description:
	Map the SQS to the desinated event

	:param message: [type: dict] the general message from lambda function
	:param extra: [type: dict] extra message info depened on the type (e.g. process or network activity)

	'''	
	event_id = str(uuid.uuid1())

	data = {}
	data['event_id'] = event_id
	data['device_id'] = message['device_id']
	data['time_processed'] = datetime.utcnow().isoformat()
	if('cmdl' in extra.keys() and 
		'user' in extra.keys()):
		data['type'] = "new_process"
		data['cmdl'] = extra['cmdl']
		data['user'] = extra['user']
	elif ('source_ip' in extra.keys() and
			'source_ip' in extra.keys() and 
			'destination_port' in extra.keys()):
		data['type'] = "network_connection"
		data['source_ip'] = extra['source_ip']
		data['destination_ip'] = extra['destination_ip']
		data['destination_port'] = extra['destination_port']
	else:
		# unkown message type. drop it.
		raise TypeError("Undified source event type")
	
	event = {'Data': {}, 'PartitionKey': event_id}
	event['Data'] = json.dumps(data)
	return event
```
`map_event` function is responsible to map the incoming message to the below output format:

```json
{
    "event_id": "<uuid>",                  # unique identifier of the event (string)
    "device_id": "<uuid>",                 # unique identifier of the device (string)
    "time_processed": "<ISO 8601>",        # creation time of the event, server local time in UTC (string)
    "type": "string",                      # type of event: possbile values is new_process or network_connection

    "details":
      {
          "cmdl": "<commandline>",         # command line of the executed process (string)
          "user": "<username>"             # username who started the process (string)
      },
            ...
        or ...
      {
          "source_ip": "<ipv4>",           # source ip of the network connection, e.g. "192.168.0.1" (string)
          "destination_ip": "<ipv4>",      # destination ip of the network connection, e.g. "142.250.74.110" (string)
          "destination_port": <0-65535>    # destination port of the network connection, e.g. 443 (integer)
      },
            ...
}
```

Finally, you can use `template.yaml` file to configure your application deployment:

```yaml
Resources:
  SubmissionToEventsFunction:
    Type: AWS::Serverless::Function
    Properties:
      Handler: app.lambda_handler
      Runtime: python3.9
      Events:
        SQSEvent:
          Type: SQS
          Properties:
            Queue: arn:aws:sqs:us-west-1:000000000000:submissions
            BatchSize: 10
```
* **Queue**: is the sqs name.
* **BatchSize**: the queue batch size per request. Default is 10 and maximum is 1000.

If you prefer to use an integrated development environment (IDE) to build and test your application, you can use the AWS Toolkit.  
The AWS Toolkit is an open source plug-in for popular IDEs that uses the SAM CLI to build and deploy serverless applications on AWS. The AWS Toolkit also adds a simplified step-through debugging experience for Lambda function code. See the following links to get started.

* [VS Code](https://docs.aws.amazon.com/toolkit-for-vscode/latest/userguide/welcome.html)


The idea here is to create a aws lambda function the listen to incoming messages (submissions queue), process and prepare the data for submission to kinesis events.

receive_message()


## Configure Role

aws configure

```console
$ awslocal s3 mb s3://deploy-bucket
$ awslocal s3 cp TelemetryAccessRole.json s3://deploy-bucket
$ awslocal iam create-role --role-name TelemetryAccessRole \
			--assume-role-policy-document file:////tmp/localstack/TelemetryAccessRole.json
```

## Deploy

```console
$ zip -r telemetry-mapping.zip submissions_to_events/__init__.py submissions_to_events/app.py
```

```console
$ awslocal lambda create-function \
	--function-name TelemetryMapping \
	--zip-file fileb://./telemetry-mapping.zip \
	--handler app.lambda_handler \
	--runtime python3.8 \
	--role TelemetryAccessRole

$ awslocal lambda invoke --function-name TelemetryMapping --cli-binary-format raw-in-base64-out  --payload file://./events/event.json response.json

$ awslocal kinesis get-shard-iterator --shard-id shardId-000000000000 --shard-iterator-type TRIM_HORIZON --stream-name events

$ aws kinesis get-records --shard-iterator XXXXXXX
```

```console
$ awslocal lambda create-event-source-mapping \
	--event-source-arn arn:aws:sqs:us-west-1:000000000000:submissions	\
	--function-name TelemetryMapping \
	--batch-size 5

```
## Debugging
before executing the docker-compose command, define the following environment variables:

LAMBDA_REMOTE_DOCKER=0
LAMBDA_DOCKER_FLAGS='-p 19891:19891'
DEBUG=1

Visual Studio
.env
lanunch.json

https://docs.localstack.cloud/tools/lambda-tools/debugging/

***
what about security???

* each event is published as an individual record to kinesis (one submission is turned into multiple events)
* each event must have information of the event type (`new_process` or `network_connection`)
* each event must have an unique identifier
* each event must have an identifier of the source device (`device_id`)
* each event must have a timestamp when it was processed (backend side time in UTC)
* submissions are validated and invalid or broken submissions are dropped
* must guarantee no data loss (for valid data), i.e. submissions must not be deleted before all events are succesfully published
	
* must guarantee ordering of events in the context of a single submission

* the number of messages read from SQS with a single request must be configurable
	use BatchSize in CreateEventSourceMapping to configure the size of sqs batch as per the requirments

* the visibility timeout of read SQS messages must be configurable
	# this is the function to change visibility (in seconds)
	change_message_visibility()

***
Extra

* How does your application scale and guarantee near-realtime processing when the incoming traffic increases? Where are the possible bottlenecks and how to tackle those?
* What kind of metrics you would collect from the application to get visibility to its througput, performance and health?
* How would you deploy your application in a real world scenario? What kind of testing, deployment stages or quality gates you would build to ensure a safe production deployment?

## Further enhancements
1. not valid outputs can be directed to another diagnostic queue

## Deploy the sample application

The Serverless Application Model Command Line Interface (SAM CLI) is an extension of the AWS CLI that adds functionality for building and testing Lambda applications. It uses Docker to run your functions in an Amazon Linux environment that matches Lambda. It can also emulate your application's build environment and API.

To use the SAM CLI, you need the following tools.

* SAM CLI - [Install the SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/serverless-sam-cli-install.html)
* [Python 3 installed](https://www.python.org/downloads/)
* Docker - [Install Docker community edition](https://hub.docker.com/search/?type=edition&offering=community)

To build and deploy your application for the first time, run the following in your shell:

```bash
sam build --use-container
sam deploy --guided
```

The first command will build the source of your application. The second command will package and deploy your application to AWS, with a series of prompts:

* **Stack Name**: The name of the stack to deploy to CloudFormation. This should be unique to your account and region, and a good starting point would be something matching your project name.
* **AWS Region**: The AWS region you want to deploy your app to.
* **Confirm changes before deploy**: If set to yes, any change sets will be shown to you before execution for manual review. If set to no, the AWS SAM CLI will automatically deploy application changes.
* **Allow SAM CLI IAM role creation**: Many AWS SAM templates, including this example, create AWS IAM roles required for the AWS Lambda function(s) included to access AWS services. By default, these are scoped down to minimum required permissions. To deploy an AWS CloudFormation stack which creates or modifies IAM roles, the `CAPABILITY_IAM` value for `capabilities` must be provided. If permission isn't provided through this prompt, to deploy this example you must explicitly pass `--capabilities CAPABILITY_IAM` to the `sam deploy` command.
* **Save arguments to samconfig.toml**: If set to yes, your choices will be saved to a configuration file inside the project, so that in the future you can just re-run `sam deploy` without parameters to deploy changes to your application.

You can find your API Gateway Endpoint URL in the output values displayed after deployment.

## Use the SAM CLI to build and test locally

Build your application with the `sam build --use-container` command.

```bash
telemetry-mapping$ sam build --use-container
```

The SAM CLI installs dependencies defined in `submissions_to_events/requirements.txt`, creates a deployment package, and saves it in the `.aws-sam/build` folder.

Test a single function by invoking it directly with a test event. An event is a JSON document that represents the input that the function receives from the event source. Test events are included in the `events` folder in this project.

Run functions locally and invoke them with the `sam local invoke` command.

```bash
telemetry-mapping$ sam local invoke SubmissionToEventsFunction --event events/event.json
```

The SAM CLI can also emulate your application's API. Use the `sam local start-api` to run the API locally on port 3000.

## Fetch, tail, and filter Lambda function logs

To simplify troubleshooting, SAM CLI has a command called `sam logs`. `sam logs` lets you fetch logs generated by your deployed Lambda function from the command line. In addition to printing the logs on the terminal, this command has several nifty features to help you quickly find the bug.

`NOTE`: This command works for all AWS Lambda functions; not just the ones you deploy using SAM.

```bash
telemetry-mapping$ sam logs -n SubmissionToEventsFunction --stack-name telemetry-mapping --tail
```

You can find more information and examples about filtering Lambda function logs in the [SAM CLI Documentation](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/serverless-sam-cli-logging.html).

## Resources

See the [AWS SAM developer guide](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/what-is-sam.html) for an introduction to SAM specification, the SAM CLI, and serverless application concepts.

Next, you can use AWS Serverless Application Repository to deploy ready to use Apps that go beyond hello world samples and learn how authors developed their applications: [AWS Serverless Application Repository main page](https://aws.amazon.com/serverless/serverlessrepo/)

## Design Consideration


Using lambda fuction for this application makes it compatiable and well integrated. In case of multi-cloud setup, we would recommend
open source tools like `Kafka` and `Prometheus`
