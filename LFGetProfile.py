# This file is designed for the lambda function to get user profile information
# in the project CUThen, the final project for COMSE6998_010_2023_3,
# Topics in Computer Science: Cloud Computing and Big Data.

import json
import os
import string
import boto3
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth
from botocore.exceptions import ClientError

REGION = 'us-east-1'
HOST = 'search-cuthen-temp-5fyo5fvs7x7t2myle4ztwa7swa.us-east-1.es.amazonaws.com'
INDEX1 = 'user_to_group'
INDEX2 = 'user_to_inv'
INDEX3 = 'group_to_user'

def get_awsauth(region, service):
    cred = boto3.Session().get_credentials()
    return AWS4Auth(cred.access_key,
                    cred.secret_key,
                    region,
                    service,
                    session_token=cred.token)

def lookup_data(key, db=None, table='user_table'):
    if not db:
        db = boto3.resource('dynamodb')
    table = db.Table(table)
    try:
        response = table.get_item(Key=key)
    except ClientError as e:
        print('Error', e.response['Error']['Message'])
        return False
    else:
        print(f"RESPONSE: {response}")
        ret = response['Item']
        ret['user_id'] = int(ret['user_id'])
        return ret

def query(client, index, field, term):
    q = {"query": {
            "bool": {
                "must": {
                    "match": {
                        field: term
                    }
                }
            }
        }
    }

    res = client.search(index=index, body=q)
    print(res)

    hits = res['hits']['hits']
    print(f"hits: {hits}")
    if len(hits) == 0:
        return False
    return hits[0]['_source']

def get_user(userId):
    user = {}
    userInfo = lookup_data(key = {"user_id": userId}, table='user_table')
    print(f"userInfo from DynamoDB: {userInfo}")
    user['userId'] = userInfo['user_id']
    user['userName'] = userInfo['first_name'] + ' ' + userInfo['last_name']
    user['userFeatures'] = [{k: v} for k, v in userInfo.items()]
    return user

def get_group(client, groupId):
    group = {}
    gobj = query(client=client, index=INDEX3, field='group_id', term=str(groupId))
    if gobj:
        gleader = get_user(gobj['leader_id'])
        gmember = []
        for mid in gobj['user_id']:
            gmember.append(get_user(mid))
        group['groupId'] = int(groupId)
        group['groupLeader'] = gleader
        group['groupMembers'] = gmember
        print(f"Group: {group}")
        return group
    return {}

def lambda_handler(event, context):
    print(f"Event: {event}")
    userId = json.loads(event['body'])
    userId = userId['userId']
    currentUser = get_user(int(userId))
    print(f"Current user: {currentUser}")
    ret = {}

    os_client = OpenSearch(hosts=[{
        'host': HOST,
        'port': 443
    }],
                        http_auth=get_awsauth(REGION, 'es'),
                        use_ssl=True,
                        verify_certs=True,
                        connection_class=RequestsHttpConnection)

    user_to_group = query(client=os_client, index=INDEX1, field='user_id', term=str(userId))
    user_to_inv = query(client=os_client, index=INDEX2, field='user_id', term=str(userId))
    groups = []
    invs = []
    for gid in user_to_group['group_id']:
        cur_group = get_group(os_client, gid)
        if len(cur_group) > 0:
            groups.append(get_group(os_client, gid))
    
    for iid in user_to_inv['pending_inv_ids']:
        invs.append({
            'invitingGroup': get_group(os_client, iid),
            'invitee': currentUser
        })
    ret['groups'] = groups
    ret['userName'] = currentUser['userName']
    ret['userFeatures'] = currentUser['userFeatures']
    ret['pendingInvites'] = invs

    print(f"Response: {ret}")

    return {
        'statusCode': 200,
        "headers": {"Access-Control-Allow-Origin": "*"},
        'body': json.dumps(ret)
    }
