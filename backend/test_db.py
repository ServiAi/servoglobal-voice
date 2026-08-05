import os
import sys
from sqlalchemy import create_engine, text

engine = create_engine(os.environ['STAGING_DATABASE_URL'])
with engine.connect() as conn:
    print('Users:', conn.execute(text('SELECT id, external_auth_id, email FROM users LIMIT 5')).fetchall())
    print('Tenants:', conn.execute(text('SELECT id, name FROM tenants LIMIT 5')).fetchall())
    print('TenantMemberships:', conn.execute(text('SELECT user_id, tenant_id FROM tenant_memberships LIMIT 5')).fetchall())
