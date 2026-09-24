import boto3

client = boto3.client(
    "s3",
    endpoint_url="http://localhost:9000",
    aws_access_key_id="lakeuser",
    aws_secret_access_key="MinIOUser123##",
)

response = client.list_buckets()

# client.delete_bucket(Bucket="raw")
for bucket in response["Buckets"]:
    print(bucket["Name"])