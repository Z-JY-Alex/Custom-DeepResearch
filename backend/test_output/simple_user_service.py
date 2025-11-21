"""
用户管理服务模块
"""
import hashlib
class UserRole:
    ADMIN = 'admin'
    MODERATOR = 'moderator'
    USER = 'user'
    GUEST = 'guest'

class UserService:
    def hash_password(self, password):
        return hashlib.sha256(password.encode()).hexdigest()
        
    def validate_email(self, email):
        return '@' in email
        
    def validate_username(self, username):
        return len(username) >= 3
