



awslocal s3 mb s3://deploy-bucket
awslocal s3 cp TelemetryAccessRole.json s3://deploy-bucket
awslocal iam create-role --role-name TelemetryAccessRole \
		--assume-role-policy-document s3://deploy-bucket/TelemetryAccessRole.json

awslocal lambda delete-function \
			--function-name TelemetryMapping

rm telemetry-mapping.zip

zip -r -j telemetry-mapping.zip submissions_to_events/__init__.py submissions_to_events/app.py

awslocal lambda create-function \
		--function-name TelemetryMapping \
		--zip-file fileb://./telemetry-mapping.zip \
		--handler app.lambda_handler \
		--runtime python3.8 \
		--environment "Variables={AWS_DEFAULT_REGION=eu-west-1,AWS_ACCESS_KEY_ID=some_key_id,AWS_SECRET_ACCESS_KEY=some_secret,ENDPOINT_URL=http://localstack:4566}" \
		--role TelemetryAccessRole \

