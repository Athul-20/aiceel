import sqlite3
conn = sqlite3.connect(r"c:\Users\Admin\Documents\aiceel\AICCEL_SAAS\saas-backend\aiccel_saas.db")
c = conn.cursor()

# Check all users
c.execute("SELECT id, email, default_workspace_id FROM users")
users = c.fetchall()
print("Users:")
for u in users:
    print(f"  id={u[0]}, email={u[1]}, workspace={u[2]}")

# Check provider credentials with details
c.execute("SELECT id, user_id, workspace_id, provider, key_last4, is_active FROM provider_credentials")
creds = c.fetchall()
print("\nProvider credentials:")
for cr in creds:
    print(f"  id={cr[0]}, user_id={cr[1]}, workspace_id={cr[2]}, provider={cr[3]}, last4={cr[4]}, active={cr[5]}")

conn.close()
 