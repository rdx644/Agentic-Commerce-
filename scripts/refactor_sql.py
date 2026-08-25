import os
import re

def process_file(filepath):
    with open(filepath, 'r') as f:
        content = f.read()
    
    # Simple replacement of '?' with '%s' where they appear as bind parameters
    # This regex looks for ? that are not in a comment or string literal 
    # Actually, a simpler approach for these specific files is to just replace '?' 
    # where it's part of an execute() string.
    
    # We will just manually define the replacements per file to be perfectly safe.

    # 1. src/webhook/handler.py
    if "webhook/handler.py" in filepath.replace('\\', '/'):
        content = content.replace("= ?", "= %s")
        content = content.replace("VALUES (?, ?, ?, 1)", "VALUES (%s, %s, %s, 1)")
        content = content.replace("VALUES (?, ?, ?, ?, ?, ?, ?, ?)", "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)")
        content = content.replace("COALESCE(?,", "COALESCE(%s,")
        content = content.replace("datetime('now')", "NOW()")
        
    # 2. src/upsell/service.py
    elif "upsell/service.py" in filepath.replace('\\', '/'):
        content = content.replace("VALUES (?, ?, ?, ?, ?, ?)", "VALUES (%s, %s, %s, %s, %s, %s)")
        content = content.replace("VALUES (?, ?, ?, ?, ?, ?, ?)", "VALUES (%s, %s, %s, %s, %s, %s, %s)")

    # 3. src/payment/service.py
    elif "payment/service.py" in filepath.replace('\\', '/'):
        content = content.replace("VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)")
        content = content.replace("VALUES (?, ?, ?, ?, 'PENDING')", "VALUES (%s, %s, %s, %s, 'PENDING')")
        content = content.replace("= ?", "= %s")
        content = content.replace("datetime('now')", "NOW()")
        
    # 4. src/payment/reconciliation.py
    elif "payment/reconciliation.py" in filepath.replace('\\', '/'):
        content = content.replace("= ?", "= %s")
        content = content.replace("VALUES (?, ?, ?, ?, ?, ?, ?)", "VALUES (%s, %s, %s, %s, %s, %s, %s)")
        content = content.replace("VALUES (?, ?, ?, ?, ?)", "VALUES (%s, %s, %s, %s, %s)")
        content = content.replace("datetime('now')", "NOW()")
        # Special case: created_at < datetime('now', ? || ' seconds')
        content = content.replace("created_at < datetime('now', %s || ' seconds')", "created_at < NOW() - (%s || ' seconds')::interval")
        content = content.replace("created_at < datetime('now', ? || ' seconds')", "created_at < NOW() - (%s || ' seconds')::interval")
        
    # 5. src/guardrail/service.py
    elif "guardrail/service.py" in filepath.replace('\\', '/'):
        content = content.replace("VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)")

    # 6. src/guardrail/ledger.py
    elif "guardrail/ledger.py" in filepath.replace('\\', '/'):
        content = content.replace("spent_paise + ?", "spent_paise + %s")
        content = content.replace("session_id = ?", "session_id = %s")
        content = content.replace("VALUES (?, ?, ?, 0, 0, 0)", "VALUES (%s, %s, %s, 0, 0, 0)")

    # 7. src/catalog/service.py
    elif "catalog/service.py" in filepath.replace('\\', '/'):
        content = content.replace("VALUES (?, ?, ?)", "VALUES (%s, %s, %s)")
        content = content.replace("version = ?", "version = %s")

    # 8. src/campaign/orchestrator.py
    elif "campaign/orchestrator.py" in filepath.replace('\\', '/'):
        content = content.replace("VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)")
        content = content.replace("campaign_id = ?", "campaign_id = %s")

    # 9. src/audit/service.py
    elif "audit/service.py" in filepath.replace('\\', '/'):
        content = content.replace("session_id = ?", "session_id = %s")
        content = content.replace("action = ?", "action = %s")
        content = content.replace("failure_class = ?", "failure_class = %s")
        content = content.replace("LIMIT ? OFFSET ?", "LIMIT %s OFFSET %s")
        
    # 10. src/audit/router.py
    elif "audit/router.py" in filepath.replace('\\', '/'):
        content = content.replace("id > ?", "id > %s")

    with open(filepath, 'w') as f:
        f.write(content)

src_dir = os.path.join(os.path.dirname(__file__), "..", "src")
for root, _, files in os.walk(src_dir):
    for file in files:
        if file.endswith('.py'):
            process_file(os.path.join(root, file))
print("Done")
