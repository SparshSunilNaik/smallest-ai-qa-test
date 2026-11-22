import requests

url = "https://api.smallest.ai/waves/v1/stt/"

headers = {
    "Authorization": "Bearer <BearerAuth>",
    "Content-Type": "application/octet-stream"
}

response = requests.post(url, headers=headers)

print(response.json())
