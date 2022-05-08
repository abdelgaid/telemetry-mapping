
# zip -r telemetry-reformat.zip lambda_function.py sqs_to_kinesis_mapping.json requirements.txt requirements.in

awslocal lambda delete-function \
			--function-name TelemetryMapping

awslocal lambda create-function \
	--function-name TelemetryMapping \
	--zip-file fileb://./telemetry-mapping.zip \
	--handler app.lambda_handler \
	--runtime python3.8 \
	--role TelemetryAccessRole
