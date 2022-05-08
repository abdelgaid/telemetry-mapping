import boto3
import traceback
import json
import os
import uuid
from datetime import datetime

# import requests
kinesis_client = boto3.client('kinesis')

EVENT_STREAM_NAME = 'events'


def extract_data(record):
	'''
	Description:
	This function performs the data extraction from the record dictionary

	:param record: [type: dict] corresponds to a message from a list of messages read by lambda

	'''
	body = json.loads(record['Body'])
	return body

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


def add_message(record, kinesis_records_all):
	'''
	Description: 
	This function extracts the required data from the record dictionary and adds it to the list of records 
	to be pushed to the respective mapped Kinesis Data Stream based. 
	If data extraction throws exception then the whole record dictionary is not processed and eventually to be dropped.

	:param record: [type: dict] corresponds to a message from a list of messages read by lambda
	
	:param kinesis_records_all: [type: dict] contains sqs queue arns as keys mapped to a dict containing list of records 
			      	   to be pushed and the name of the destination Kinesis Data Stream

	:return kinesis_records_all: [type: dict] updated dict kinesis_records_all 
	'''
	#creating record_dict dictionary
	record_dict = {}
	try:
		#Retrieving required message_id and body from record.
		record_dict['MessageId'] = record['MessageId']
		body = extract_data(record)
		
		events_list = []
		for process in body['events']['new_process']:
			event = map_event(body, process)
			events_list.append(event)
		
		for network_connection in body['events']['network_connection']:
			event = map_event(body, network_connection)
			events_list.append(event)

		record_dict['events'] = events_list
		# submission is successfull add it to our list
		kinesis_records_all['valid'].append(record_dict)
		print(f"Successfully processed message_id : {record_dict['MessageId']}")
	except Exception as e:
		# vaild messages will be removed automatically after visibility time

		# log exceptions
		message = '\n'.join([str(e), str(traceback.print_exc())])
		print(message)
	finally:
		return kinesis_records_all


def push_to_kinesis(kinesis_records_all):
	'''
	Description:
	This function pushes the list of extracted records from a queue / non_conformed records to a particular 
	Kinesis Data Stream
	
	:param kinesis_records_all: [type: str] SQS queue ARN
	'''

	failed_list = {"batchItemFailures": [] }
	for source in kinesis_records_all['valid']:
		try:
			response = kinesis_client.put_records(Records = source['events'], StreamName = EVENT_STREAM_NAME)

			if response["ResponseMetadata"]["HTTPStatusCode"] == 200:
				print(f"Successfully submitted message_id : {source['MessageId']}")
		except Exception as e:
			# keep faild events submission only.
			itemIdentifier = source['MessageId']
			failed_list['batchItemFailures'].append({"itemIdentifier": itemIdentifier})
	
	return failed_list


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


