"""Shared HTTP response headers."""
import json

def response(code,body,content_type='application/json'):
    return dict(statusCode=code,headers={'content-type':content_type,'cache-control':'no-store','content-security-policy':"default-src 'self'; connect-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'",'x-content-type-options':'nosniff'},body=json.dumps(body,allow_nan=False) if content_type=='application/json' else body)

