import pywhatkit as kit
import os
# 1. List of recipients
contacts = [
    "+918849083319"
]

# 2. Read content from README.md (text part only)
with open(r"E:\loganalyzer\crewaiLogsReport\reports\performance_report.md", "r", encoding="utf-8") as file:
    content = file.read()

# Optional: Trim the content if it's too long for WhatsApp (limit to 3000 characters or so)
max_length = 10000
message = content[:max_length]

# 3. Send the message instantly
for contact in contacts:
    try:
        kit.sendwhatmsg_instantly(contact, message, wait_time=10, tab_close=True)
        print(f"README.md content sent to {contact}")
    except Exception as e:
        print(f"Error with {contact}: {e}")
