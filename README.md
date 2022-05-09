# Telemetry mapping

This project contains source code and supporting files for a telemetry mapping of SQS queue `sensor-fleet` to kinesis stream `events`. 
You can deploy with the SAM CLI. The projects includes the following files and folders.

- `submissions_to_events` - Code for the application's Lambda function.
- `events` - Invocation events that you can use as sample inpunt to invoke the function.
- `template.yaml` - A template that defines the application's AWS resources.

## Development Overview
We have used AWS lambda function to make this service. The function can read continuously from SQS queue map this data to
Kinesis event stream. The following are snippts from the code `submissions_to_events/app.py`:

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
`lambda_handler` is the main function that receive the request. We record all successfully processed records to `valid` list. `failed` 
list will contain events that failed to be submitted to Kinesis. At the end we return the list of valid but failed submissions.
This indicate to Lambda hanler to keep those messages in the queue for further retry.

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
		data['details'] = {}
		data['details']['cmdl'] = extra['cmdl']
		data['details']['user'] = extra['user']
	elif ('source_ip' in extra.keys() and
			'source_ip' in extra.keys() and 
			'destination_port' in extra.keys()):
		data['type'] = "network_connection"
		data['details'] = {}
		data['details']['source_ip'] = extra['source_ip']
		data['details']['destination_ip'] = extra['destination_ip']
		data['details']['destination_port'] = extra['destination_port']
	else:
		# unkown message type. drop it.
		raise TypeError("Undified source event type")
	
	event = {'Data': {}, 'PartitionKey': event_id}
	event['Data'] = json.dumps(data)
	return event
```

`map_event` function is responsible to map the incoming message to the below output.

**Note**: We need further enhancements for message validations of items like number, time and ip address formats.

### Output JSON format
The output is formated as json as following:

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
### Debuging
Finally, you can use `template.yaml` file to debug and test your application:

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
The AWS Toolkit is an open source plug-in for popular IDEs that uses the SAM CLI to build and deploy serverless applications on AWS. 
The AWS Toolkit also adds a simplified step-through debugging experience for Lambda function code. See the following links to get started.

* [VS Code](https://docs.aws.amazon.com/toolkit-for-vscode/latest/userguide/welcome.html)


The idea here is to create a aws lambda function the listen to incoming messages (submissions queue), process and prepare the data for submission to kinesis events.

**Note**: SAM for some reason doesn't work with `localstack`, which needs more investation. So for `localstack` deployments, we will use `aws` and `awslocal` commands.

## Local Deployment

For this steps, we need to install `awslocal` tool:

```console
$ pip install awscli-local
```

Now ensure that environment variables for the command line is defined:

 - `AWS_DEFAULT_REGION`
 - `AWS_ACCESS_KEY_ID`
 - `AWS_SECRET_ACCESS_KEY`

**Note**: ensure that path `~/.local/bin` is added to `PATH` environment variable.

### Create access role

```console
$ awslocal s3 mb s3://deploy-bucket
$ awslocal s3 cp TelemetryAccessRole.json s3://deploy-bucket
$ awslocal iam create-role --role-name TelemetryAccessRole \
		--assume-role-policy-document s3://deploy-bucket/TelemetryAccessRole.json

```
### Package and deploy		
```console
$ zip -r -j telemetry-mapping.zip submissions_to_events/__init__.py submissions_to_events/app.py
```
Deploy the lambda function `telemetry-mapping.zip` to `localstack`

```console
$ awslocal lambda create-function \
		--function-name TelemetryMapping \
		--zip-file fileb://./telemetry-mapping.zip \
		--handler app.lambda_handler \
		--runtime python3.8 \
		--environment "Variables={AWS_DEFAULT_REGION=eu-west-1,AWS_ACCESS_KEY_ID=some_key_id,AWS_SECRET_ACCESS_KEY=some_secret,ENDPOINT_URL=http://localstack:4566}" \
		--role TelemetryAccessRole \


```
### Invoke and Test
Invoke the function to check it is running correctly.

```console
$ awslocal lambda invoke --function-name TelemetryMapping \
			--cli-binary-format raw-in-base64-out \
			--payload file://./events/event.json response.json
```

Now you can check the kinesis `event` has been created.

```console
$ awslocal kinesis get-shard-iterator --shard-id shardId-000000000000 --shard-iterator-type TRIM_HORIZON --stream-name events
{
    "ShardIterator": "XXXXXXX"
}

$ awslocal kinesis get-records --shard-iterator XXXXXXX
```

### Consuming Messages

After all the previous commands are successful, we can now map the service to the input queue. Not that `--batch-size` parameter is used to configure
the number of messages per request.

```console
$ awslocal lambda create-event-source-mapping \
	--event-source-arn arn:aws:sqs:eu-west-1:000000000000:submissions \
	--function-name TelemetryMapping \
	--batch-size 5

```

## Design Consideration

### Service scalability

AWS scale the lambda function automatically according to the traffic. Here is a breif about the scalability:

https://docs.aws.amazon.com/lambda/latest/dg/invocation-scaling.html

However, if the size of the batch is large, we recommend to change the code to submit each message after parsing phase. So, we dont't 
impcat the cache of the lambda service.


**Note**:Using lambda fuction for this application makes it compatiable and well integrated with current setup. However, in case of multi-cloud setup, we would recommend
open source tools like `Kafka` and `Prometheus`, which works well in diverse environment.

### Matrics collections
We recommend the collection of the following to get better insight in the service behavior:

* The latency between message addition to the queue and time of submission to the event stream. This indicate how fast the service consume and process the messages
* Number of valid messages to parse along with the `device_id`. This will indicate if we have a device that send wrong data frequently.
* Number of failures to submit the events. Since this messages will be kept and retries to process them again.

### Production Deployment
The application needs a unit test to ensure the quality of the development. We can integrate this test along with a CI/CD like Jenkins. This ensure the quality of deployment 
on testing and staging.

For production deployment, we should use blue/green deployment. In this case, we will deploy both the old and new version. This allow us to monitor the new service status and 
rollback safely and fast in case of failures.

## Further enhancements
1. not valid outputs can be directed to another diagnostic queue


