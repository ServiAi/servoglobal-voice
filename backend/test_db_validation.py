import os
import sys
from sqlalchemy import create_engine, text

engine = create_engine(os.environ['STAGING_DATABASE_URL'])

queries = {
    '1. Agents count': 'SELECT COUNT(*) FROM agents',
    '2. Calls count': 'SELECT COUNT(*) FROM calls',
    '3. Call events count': 'SELECT COUNT(*) FROM call_events',
    '4. Metric snapshots count': 'SELECT COUNT(*) FROM metric_snapshots_daily',
    '5. Calls by normalized_status': 'SELECT normalized_status, COUNT(*) FROM calls GROUP BY normalized_status',
    '6. Calls by agent_id': 'SELECT agent_id, COUNT(*) FROM calls GROUP BY agent_id',
    '7. Calls across multiple days': 'SELECT DATE(started_at) as call_day, COUNT(*) FROM calls GROUP BY call_day ORDER BY call_day DESC LIMIT 5',
    '8. Calls across multiple hours': 'SELECT EXTRACT(HOUR FROM started_at) as call_hour, COUNT(*) FROM calls GROUP BY call_hour ORDER BY call_hour LIMIT 5',
    '9. Calls with billed_minutes': 'SELECT COUNT(*) FROM calls WHERE billed_minutes IS NOT NULL',
    '10. Calls with summary': 'SELECT COUNT(*) FROM calls WHERE summary IS NOT NULL OR short_summary IS NOT NULL',
}

try:
    with engine.connect() as conn:
        for name, query in queries.items():
            print(f"--- {name} ---")
            result = conn.execute(text(query)).fetchall()
            for row in result:
                print(row)
            print()
except Exception as e:
    print(f"Error connecting or executing: {e}")
