import json
import os
import re
from datetime  import datetime, timedelta
from botocore.exceptions import ClientError
import boto3

myAccount = boto3.client('sts').get_caller_identity()['Account']
ec2 = boto3.resource("ec2")
client = boto3.client('ec2')
snapshots = client.describe_snapshots(OwnerIds=[myAccount])

def lambda_handler(event, context):
    
    # Gather AMIs and figure out which ones to delete
    my_images = ec2.images.filter(Owners=[myAccount])

    # Don't delete images in use
    used_images = {
        instance.image_id for instance in ec2.instances.all()
    }

    # Keep everything younger 200 days
    young_images = set()
    for image in my_images:
        created_at = datetime.strptime(
            image.creation_date,
            "%Y-%m-%dT%H:%M:%S.000Z",
        )
        if created_at > datetime.now() - timedelta(200):
            young_images.add(image.id)

    # Keep latest one
    latest = dict()
    for image in my_images:
        split = image.name.split('-')
        try:
            timestamp = int(split[-1])
        except ValueError:
            continue
        name = '-'.join(split[:-1])
        if(
                name not in latest
                or timestamp > latest[name][0]
        ):
            latest[name] = (timestamp, image)
    latest_images = {image.id for (_, image) in latest.values()}

    # Delete everything
    safe = used_images | young_images | latest_images
    for image in (
        image for image in my_images if image.id not in safe
    ):
        print('Deregistering {} ({})'.format(image.name, image.id))
        image.deregister()

    # Delete unattached snapshots
    for snapshot in snapshots['Snapshots']:
        start_time_snapshots = snapshot['StartTime']
        date_snapshots = start_time_snapshots.date()
        date_of_snapshots = datetime.now().date()
        diff_snapshots = date_of_snapshots-date_snapshots
        conv_day_snapshots = start_time_snapshots.day
        try:
            if diff_snapshots.days>200 and conv_day_snapshots!=1:
                id = snapshot['SnapshotId']
                print("Deleting Sapshots\t"+id)
                client.delete_snapshot(SnapshotId=id)
        except ClientError as e:
                print("Unexpected error: %s Skipping this snapshot" % e)
                continue
        
