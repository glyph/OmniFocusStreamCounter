from ofprogress import doc
from appscript import its
from time import sleep
from datetime import datetime

def main() -> None:
    then = datetime.now()
    while True:
        sleep(10)
        now = datetime.now()
        print(f"tick from {then.isoformat()} to {now.isoformat()}")
        for task in doc.flattened_tasks[its.modification_date > then]():
            print(f"changed: {task.name()}")
        then = now


if __name__ == "__main__":
    main()
