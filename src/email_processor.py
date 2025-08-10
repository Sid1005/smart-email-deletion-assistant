import yaml
import os
from datetime import datetime
from dotenv import load_dotenv
from src.gmail_client import GmailClient
from src.groq_analyzer import GroqAnalyzer
from src.database import EmailDatabase

class EmailProcessor:
    def __init__(self, config_path="config/config.yaml"):
        """Initialize email processor with configuration"""
        # Load environment variables from .env file
        load_dotenv()
        # Load config first
        with open(config_path, 'r') as file:
            self.config = yaml.safe_load(file)
        
        # Gmail client with correct path
        self.gmail_client = GmailClient(
            credentials_file="config/credentials.json",  # Fixed path
            scopes=self.config['gmail']['scopes']
        )
        
        # Groq analyzer with API key from environment
        groq_api_key = os.getenv('GROQ_API_KEY')
        if not groq_api_key:
            raise ValueError("GROQ_API_KEY environment variable is required")
        
        self.groq_analyzer = GroqAnalyzer(
            api_key=groq_api_key,  # Added API key
            model=self.config['groq']['model']
        )
        
        # Database
        self.db = EmailDatabase(self.config['database']['path'])
        
        print("EmailProcessor initialized successfully")
    
    def _apply_preprocessing_filters(self, emails):
        """Apply preprocessing filters to emails"""
        filtered_emails = []
        protected_senders = self.config.get('deletion_rules', {}).get('protected_senders', [])
        
        for email in emails:
            # Check if sender is protected
            sender_is_protected = any(protected in email['sender'] for protected in protected_senders)
            
            if not sender_is_protected:
                filtered_emails.append(email)
            else:
                print(f"Skipping protected sender: {email['sender']}")
        
        return filtered_emails
    
    def run_paginated_analysis(self, page_token=None):
        """Process one page of emails at a time - simple version"""
        page_size = self.config.get('pagination', {}).get('page_size', 50)
        print(f"\nProcessing email page (size: {page_size})...")
        
        try:
            page_result = self.gmail_client.get_email_page(
                page_token=page_token,
                page_size=page_size,
                days_back=self.config['gmail']['days_to_analyze']
            )
            
            if not page_result['emails']:
                print("No emails found on this page")
                return None
                
            emails = page_result['emails']
            next_token = page_result['next_page_token']
            has_more = page_result['has_more']
            
            # Filter emails
            filtered_emails = self._apply_preprocessing_filters(emails)
            
            if not filtered_emails:
                print("No emails remaining after filtering")
                return None
            
            print("Analyzing emails with Groq AI...")
            analysis = self.groq_analyzer.analyze_emails(
                filtered_emails, 
                self.config['deletion_rules']
            )
            
            if not analysis:
                print("Failed to analyze emails - will retry this page")
                return None
            
            # Save page results
            run_id = self.db.save_page_analysis(
                filtered_emails, 
                analysis, 
                page_token,
                next_token
            )
            
            summary = self.groq_analyzer.generate_daily_summary(filtered_emails, analysis)
            
            print("Page analysis completed successfully")
            print(f"Run ID: {run_id}")
            
            return {
                'run_id': run_id,
                'emails': filtered_emails,
                'analysis': analysis,
                'summary': summary,
                'has_more_pages': has_more,
                'next_page_token': next_token,
                'page_info': f"Processed {len(filtered_emails)} emails"
            }
            
        except Exception as e:
            print(f"Error during analysis: {e}")
            print("Will retry this page on next attempt")
            return None

    def continue_from_last_page(self):
        """Continue processing from where we left off - simple version"""
        last_token = self.db.get_last_page_token()
        if last_token:
            print("Continuing from saved position...")
            return self.run_paginated_analysis(page_token=last_token)
        else:
            print("No saved position found, starting from beginning")
            return self.run_paginated_analysis()

    def get_pagination_status(self):
        """Get current pagination status - simple version"""
        stats = self.db.get_pagination_stats()
        last_token = self.db.get_last_page_token()
        
        return {
            'stats': stats,
            'can_continue': last_token is not None,
            'last_token': last_token
        }

    def execute_user_decisions(self, run_id, decisions):
        """Execute user decisions for email deletions"""
        print(f"\nExecuting user decisions for run {run_id}...")
        
        try:
            pending_run = self.db.get_pending_run()
            if not pending_run or pending_run['run'][0] != run_id:
                print("No pending run found or run ID mismatch")
                return False
            
            emails_to_delete = []
            deleted_email_info = []
            
            for email_data in pending_run['emails']:
                email_id = email_data[2]
                subject = email_data[3]
                sender = email_data[4]
                
                user_decision = decisions.get(email_id)
                if user_decision == 'delete':
                    emails_to_delete.append(email_id)
                    deleted_email_info.append((email_id, subject, sender))
            
            if emails_to_delete:
                success = self.gmail_client.delete_emails(emails_to_delete)
                if success:
                    self.db.log_deleted_emails(deleted_email_info)
                    print(f"Successfully deleted {len(emails_to_delete)} emails")
                else:
                    print("Failed to delete emails")
                    return False
            
            self.db.update_user_decisions(run_id, decisions)
            self.db.mark_run_completed(run_id)
            
            print("User decisions executed successfully")
            return True
            
        except Exception as e:
            print(f"Error executing user decisions: {e}")
            return False

    def get_pending_review(self):
        """Get pending analysis for review"""
        return self.db.get_pending_run()

    def test_connections(self):
        """Test all API connections"""
        print("Testing connections...")
        
        groq_ok = self.groq_analyzer.test_connection()
        
        try:
            test_emails = self.gmail_client.get_emails(max_results=1, days_back=1)
            gmail_ok = True
            print("Gmail API connection successful")
        except Exception as e:
            gmail_ok = False
            print(f"Gmail API connection failed: {e}")
        
        return groq_ok and gmail_ok

    def get_statistics(self):
        """Get processing statistics"""
        return self.db.get_stats()
