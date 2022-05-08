
zip -r telemetry-reformat.zip lambda_function.py sqs_to_kinesis_mapping.json requirements.txt requirements.in

aws --endpoint=http://localhost:4566 \
		lambda delete-function \
			--function-name TelemetryReformat

aws --endpoint=http://localhost:4566 \
		lambda create-function \
			--function-name TelemetryReformat \
			--zip-file fileb://./telemetry-reformat.zip \
			--handler lambda_function.lambda_handler \
			--runtime python3.9 \
			--role TelemetryReformatAccessRole

 aws --endpoint=http://localhost:4566 \
		lambda invoke \
			--function-name TelemetryReformat out \
			--log-type Tail
