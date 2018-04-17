import json

def get_slow_vbuckets(vbuckets):
    sorted_vbuckets = {}
    for vbucket in vbuckets:
        vbucket_dict =  vbuckets[vbucket]
        sorted_by_events = [(k, vbucket_dict[k]) for k in sorted(vbucket_dict, key=vbucket_dict.get, reverse=True)]
        total_events = len(sorted_by_events)
        start_time = float(sorted_by_events[total_events-1][1])
        end_time = float(sorted_by_events[0][1])
        total_time = end_time - start_time
        sorted_vbuckets[vbucket] = total_time
    sorted_vbuckets = [(k, sorted_vbuckets[k]) for k in sorted(sorted_vbuckets,
                                                                   key=sorted_vbuckets.get, reverse=True)]

    for vb in sorted_vbuckets:
        print("{} ({})".format(vb[0], vb[1]))


def get_slow_vbuckets_by_phase(vbuckets):
    sorted_vbuckets = {}
    for vbucket in vbuckets:
        vbucket_dict =  vbuckets[vbucket]
        sorted_by_events = [(k, vbucket_dict[k]) for k in sorted(vbucket_dict, key=vbucket_dict.get, reverse=True)]
        total_events = len(sorted_by_events)
        start_time = float(sorted_by_events[total_events-1][1])
        end_time = float(sorted_by_events[0][1])
        total_time = end_time - start_time
        sorted_vbuckets[vbucket] = total_time
    sorted_vbuckets = [(k, sorted_vbuckets[k]) for k in sorted(sorted_vbuckets,
                                                                   key=sorted_vbuckets.get, reverse=True)]

    for vb in sorted_vbuckets:
        vbucket = vb[0]
        all_events = vbuckets[vbucket]
        sorted_by_events = [(k, all_events[k]) for k in sorted(all_events, key=all_events.get)]
        #print("{} : {} : {}".format(vb[0], vb[1], sorted_by_events))
        ts = sorted_by_events[0][1]
        sorted_by_duration = {}
        for event in sorted_by_events:
            event_duration = event[1] - ts
            event_name = event[0]
            ts = event[1]
            sorted_by_duration[event_name] = event_duration
        sorted_by_duration = [(k, sorted_by_duration[k]) for k in sorted(sorted_by_duration,
                                                                         key=sorted_by_duration.get, reverse=True)]

        print("{} : {} : {}".format(vb[0], round(vb[1]), sorted_by_duration))

f = open("master_events_100_new.log", "r")
vbuckets = {}
for l in f:
    event = json.loads(l)
    if "vbucket" in event and "type" in event and "ts" in event:
        vbucket_key = event["vbucket"]
        event_vbucket_key = event["type"]
        ts = event["ts"]
        if vbucket_key not in vbuckets:
            vbuckets[vbucket_key] = {}
        vbuckets[vbucket_key][event_vbucket_key] = ts


get_slow_vbuckets_by_phase(vbuckets)






