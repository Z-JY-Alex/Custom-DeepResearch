class UserService:
    def validate_email(self, email):
        """增强的邮箱验证"""
        if not email:
            return False
        import re
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))
    def validate_username(self, username):
        return len(username) >= 3
    
    def hash_password(self, password):
        return hash(password)
