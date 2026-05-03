import redis

r = redis.Redis(host='localhost', port=6380, db=0, decode_responses=True)
p = r.pubsub()
p.subscribe('validation_events')
print("Subscribed. Waiting for events... (timeout 5s)")

for message in p.listen():
    print(message)
    # just print first message and break to avoid hanging
    if message['type'] == 'message':
        break
