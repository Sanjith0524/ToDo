import os
import datetime
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from django.conf import settings
import json
def get_google_credentials(request):
    creds = None
    token_path = f"{settings.GOOGLE_TOKEN_FILE}.{request.user.id}"
    
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_info(
            json.loads(open(token_path).read()),
            settings.GOOGLE_CALENDAR_SCOPES
        )
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                settings.GOOGLE_CREDENTIALS_FILE, 
                settings.GOOGLE_CALENDAR_SCOPES
            )
            flow.redirect_uri = 'urn:ietf:wg:oauth:2.0:oob'
            auth_url, _ = flow.authorization_url(prompt='consent')
            return None, auth_url
        
        with open(token_path, 'w') as token:
            token.write(creds.to_json())
    return creds, None

def save_token(user_id, auth_code):
    flow = InstalledAppFlow.from_client_secrets_file(
        settings.GOOGLE_CREDENTIALS_FILE,
        settings.GOOGLE_CALENDAR_SCOPES
    )
    flow.redirect_uri = 'urn:ietf:wg:oauth:2.0:oob'
    flow.fetch_token(code=auth_code)
    creds = flow.credentials
    token_path = f"{settings.GOOGLE_TOKEN_FILE}.{user_id}"
    with open(token_path, 'w') as token:
        token.write(creds.to_json())
    
    return creds

def create_google_event(creds, task):
    service = build('calendar', 'v3', credentials=creds)
    event = {
        'summary': task.title,
        'description': '',
        'start': {
            'dateTime': task.due_date.isoformat() if task.due_date else datetime.datetime.now().isoformat(),
            'timeZone': 'UTC',
        },
        'end': {
            'dateTime': (task.due_date + datetime.timedelta(hours=1)).isoformat() if task.due_date 
                        else (datetime.datetime.now() + datetime.timedelta(hours=1)).isoformat(),
            'timeZone': 'UTC',
        },
    }
    event = service.events().insert(calendarId='primary', body=event).execute()
    return event.get('id')

def update_google_event(creds, task):
    if not task.google_event_id:
        return create_google_event(creds, task)
    
    service = build('calendar', 'v3', credentials=creds)
    try:
        event = service.events().get(calendarId='primary', eventId=task.google_event_id).execute()
        event['summary'] = task.title
        event['description'] = ''  
        if task.due_date:
            event['start'] = {
                'dateTime': task.due_date.isoformat(),
                'timeZone': 'UTC',
            }
            event['end'] = {
                'dateTime': (task.due_date + datetime.timedelta(hours=1)).isoformat(),
                'timeZone': 'UTC',
            }
        if task.completed:
            event['description'] = "[COMPLETED]"
        updated_event = service.events().update(
            calendarId='primary', 
            eventId=task.google_event_id, 
            body=event
        ).execute()
        return updated_event.get('id')
    except Exception as e:
        return create_google_event(creds, task)

def delete_google_event(creds, event_id):
    if not event_id:
        return False
    
    service = build('calendar', 'v3', credentials=creds)
    try:
        service.events().delete(calendarId='primary', eventId=event_id).execute()
        import time
        time.sleep(1)
        try:
            service.events().get(calendarId='primary', eventId=event_id).execute()
            return False
        except:
            return True
    except Exception as e:
        print(f"Error deleting Google Calendar event: {str(e)}")
        return False
