import json
import sys

transcript_path = r"C:\Users\HP\.gemini\antigravity\brain\4392e3db-afb5-4f67-83fd-ca222b83128e\.system_generated\logs\transcript.jsonl"
keywords = ["500", "threshold", "treshold"]

def search_transcript():
    try:
        with open(transcript_path, "r", encoding="utf-8") as f:
            for line in f:
                for kw in keywords:
                    if kw.lower() in line.lower() and "USER_INPUT" in line:
                        data = json.loads(line)
                        if data.get("type") == "USER_INPUT":
                            print("USER:", data.get("content", "")[:200])
                            break
                    elif kw.lower() in line.lower() and "PLANNER_RESPONSE" in line:
                        data = json.loads(line)
                        if data.get("type") == "PLANNER_RESPONSE":
                            content = data.get("content", "")
                            if content:
                                print("MODEL:", content[:200])
                            break
    except Exception as e:
        print(e)

if __name__ == "__main__":
    search_transcript()
