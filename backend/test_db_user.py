import os
import sys
from sqlalchemy import create_engine, text

engine = create_engine(os.environ['STAGING_DATABASE_URL'])
with engine.connect() as conn:
    users = conn.execute(text('SELECT id, external_auth_id, email FROM users LIMIT 1')).fetchall()
    tenant_memberships = conn.execute(text('SELECT user_id, tenant_id FROM tenant_memberships LIMIT 1')).fetchall()
    print('User:', users)
    print('TenantMembership:', tenant_memberships)
