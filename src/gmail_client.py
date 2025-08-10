import os
import pickle
from datetime import datetime, timedelta
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import base64
import email
from email.mime.text import MIMEText

class GmailClient:
    def __init__(self, credentials_file, scopes):
        self.credentials_file = credentials_file
        self.scopes = scopes
        self.service = None
        self._authenticate()
    
    def _authenticate(self):
        """Authenticate with Gmail API"""
        creds = None
        token_file = 'token.pickle'
        
        # Load existing token
        if os.path.exists(token_file):
            with open(token_file, 'rb') as token:
                creds = pickle.load(token)
        
        # If no valid credentials, get new ones
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(self.credentials_file):
                    raise FileNotFoundError(f"Credentials file not found: {self.credentials_file}")
                
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_file, self.scopes)
                
                # Desktop app = can use simple localhost redirect (no manual steps!)
                creds = flow.run_local_server(port=0, open_browser=True)
            
            # Save credentials
            with open(token_file, 'wb') as token:
                pickle.dump(creds, token)
        
        # Build the service
        try:
            self.service = build('gmail', 'v1', credentials=creds)
            if self.service is None:
                raise ValueError("Failed to build Gmail service")
            print("Successfully authenticated with Gmail")
        except Exception as e:
            print(f"Error building Gmail service: {e}")
            raise
    
    def get_emails(self, max_results=100, days_back=30):
        """Fetch emails from inbox"""
        if self.service is None:
            raise ValueError("Gmail service not initialized. Authentication may have failed.")
            
        try:
            # Calculate date filter
            date_filter = datetime.now() - timedelta(days=days_back)
            query = f'in:inbox after:{date_filter.strftime("%Y/%m/%d")}'
            
            # Get message IDs
            results = self.service.users().messages().list(
                userId='me', 
                q=query, 
                maxResults=max_results
            ).execute()
            
            messages = results.get('messages', [])
            print(f"Found {len(messages)} emails to analyze")
            
            # Fetch email details
            emails = []
            for msg in messages:
                email_data = self._get_email_details(msg['id'])
                if email_data:
                    emails.append(email_data)
            
            return emails
            
        except Exception as error:
            print(f'Error fetching emails: {error}')
            return []
    
    def _get_email_details(self, message_id):
        """Get detailed email information"""
        if self.service is None:
            raise ValueError("Gmail service not initialized. Authentication may have failed.")
            
        try:
            message = self.service.users().messages().get(
                userId='me', 
                id=message_id,
                format='full'
            ).execute()
            
            headers = message['payload'].get('headers', [])
            
            # Extract key information
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
            sender = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown Sender')
            date = next((h['value'] for h in headers if h['name'] == 'Date'), '')
            
            # Get email body snippet
            snippet = message.get('snippet', '')
            
            # Check if email has been read
            labels = message.get('labelIds', [])
            is_unread = 'UNREAD' in labels
            
            return {
                'id': message_id,
                'subject': subject,
                'sender': sender,
                'date': date,
                'snippet': snippet,
                'is_unread': is_unread,
                'labels': labels
            }
            
        except Exception as error:
            print(f'Error getting email details for {message_id}: {error}')
            return None
    
    def delete_emails(self, message_ids):
        """Move emails to trash"""
        if self.service is None:
            raise ValueError("Gmail service not initialized. Authentication may have failed.")
            
        try:
            deleted_count = 0
            for msg_id in message_ids:
                self.service.users().messages().trash(
                    userId='me', 
                    id=msg_id
                ).execute()
                deleted_count += 1
            
            print(f"🗑️ Successfully moved {deleted_count} emails to trash")
            return True
            
        except Exception as error:
            print(f'Error deleting emails: {error}')
            return False
    
    def restore_emails(self, message_ids):
        """Restore emails from trash"""
        if self.service is None:
            raise ValueError("Gmail service not initialized. Authentication may have failed.")
            
        try:
            restored_count = 0
            for msg_id in message_ids:
                self.service.users().messages().untrash(
                    userId='me', 
                    id=msg_id
                ).execute()
                restored_count += 1
            
            print(f"Successfully restored {restored_count} emails")
            return True
            
        except Exception as error:
            print(f'Error restoring emails: {error}')
            return False

    def get_email_page(self, page_token=None, page_size=50, days_back=30):
        """Get one page of emails with pagination support"""
        if self.service is None:
            raise ValueError("Gmail service not initialized. Authentication may have failed.")
            
        try:
            date_filter = datetime.now() - timedelta(days=days_back)
            query = f'in:inbox after:{date_filter.strftime("%Y/%m/%d")}'
            
            query_params = {
                'userId': 'me',
                'q': query,
                'maxResults': page_size
            }
            
            if page_token:
                query_params['pageToken'] = page_token
            
            results = self.service.users().messages().list(**query_params).execute()
            
            messages = results.get('messages', [])
            next_page_token = results.get('nextPageToken')
            
            print(f"Found {len(messages)} emails on this page")
            
            # Get detailed email information
            emails = []
            for msg in messages:
                email_data = self._get_email_details(msg['id'])
                if email_data:
                    emails.append(email_data)
            
            return {
                'emails': emails,
                'next_page_token': next_page_token,
                'has_more': next_page_token is not None
            }
            
        except Exception as error:
            print(f'Error fetching email page: {error}')
            return {'emails': [], 'next_page_token': None, 'has_more': False} 
