import win32evtlog
import win32evtlogutil
import os

def export_first_200_system_logs(output_path=r"E:\loganalyzer\crewaiLogsReport\logs\syslog.log"):
    server    = 'localhost'
    log_type  = 'System'
    flags     = win32evtlog.EVENTLOG_BACKWARDS_READ | win32evtlog.EVENTLOG_SEQUENTIAL_READ

    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    hand = win32evtlog.OpenEventLog(server, log_type)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("TimeGenerated\tEventID\tSource\tType\tCategory\tMessage\n")

        count = 0
        while count < 200:
            events = win32evtlog.ReadEventLog(hand, flags, 0)
            if not events:
                break
            for ev in events:
                time   = ev.TimeGenerated.Format()
                eid    = ev.EventID & 0xFFFF
                src    = ev.SourceName
                etype  = ev.EventType
                cat    = ev.EventCategory
                msg    = "\n".join(win32evtlogutil.SafeFormatMessage(ev, log_type).splitlines())
                line   = f"{time}\t{eid}\t{src}\t{etype}\t{cat}\t{msg.replace(chr(9), ' ')}\n"
                f.write(line)
                count += 1
                if count >= 200:
                    break

    win32evtlog.CloseEventLog(hand)
    print(f"Exported first 200 logs to {output_path}")

if __name__ == "__main__":
    export_first_200_system_logs()
