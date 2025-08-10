#!/usr/bin/env python3
import argparse
import sys
import os

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.email_processor import EmailProcessor

def run_paginated_analysis():
    """Run paginated email analysis - simple version"""
    try:
        processor = EmailProcessor("config/config.yaml")
        result = processor.run_paginated_analysis()
        
        if result:
            print(f"✅ Page completed! Run ID: {result['run_id']}")
            print(f"📧 Analyzed: {len(result['emails'])} emails")
            if result['has_more_pages']:
                print("💡 Run 'python main.py --continue' for next page")
            print("🌐 Review at: http://localhost:5000/review")
            return True
        else:
            print("❌ Page analysis failed (will retry same page)")
            return False
    except Exception as e:
        print(f"Error: {e}")
        return False

def continue_pagination():
    """Continue from last page - simple version"""
    try:
        processor = EmailProcessor("config/config.yaml")
        result = processor.continue_from_last_page()
        
        if result:
            print(f"✅ Page completed! Run ID: {result['run_id']}")
            print(f"� Analyzed: {len(result['emails'])} emails")
            if result['has_more_pages']:
                print("💡 Run 'python main.py --continue' for next page")
            return True
        else:
            print("ℹ️ No more pages to process")
            return False
    except Exception as e:
        print(f"Error: {e}")
        return False

def run_analysis():
    """Run paginated email analysis (replacing old daily analysis)"""
    return run_paginated_analysis()

def test_connections():
    """Test API connections"""
    try:
        processor = EmailProcessor()  # No longer needs config path parameter
        success = processor.test_connections()
        return success
    except Exception as e:
        print(f"Connection test failed: {e}")
        return False

def show_stats():
    """Show processing statistics - simplified"""
    try:
        processor = EmailProcessor("config/config.yaml")
        stats = processor.get_statistics()
        
        print("\n📊 EMAIL PROCESSING STATISTICS")
        print("=" * 40)
        
        # Calculate pages analyzed (emails analyzed / 50)
        pages_analyzed = stats['total_emails'] // 50
        remaining_in_current = stats['total_emails'] % 50
        
        print(f"� Pages analyzed: {pages_analyzed} (50 emails each)")
        if remaining_in_current > 0:
            print(f"� Current page: {remaining_in_current} emails")
        print(f"📧 Total emails analyzed: {stats['total_emails']}")
        print(f"�️  Total emails deleted: {stats['total_deletions']}")
        print(f"✅ Emails with decisions: {stats['processed_emails']}")
        print(f"⏳ Emails pending review: {stats['pending_emails']}")
        print(f"� Recent runs (7 days): {stats['recent_runs']}")
        
        # Show pagination info
        pagination_stats = processor.get_pagination_status()
        if pagination_stats['can_continue']:
            print(f"\n� Can continue to next page: YES")
        else:
            print(f"\n💡 Can continue to next page: NO (start from beginning)")
        
        return True
    except Exception as e:
        print(f"❌ Error getting statistics: {e}")
        return False

def check_recovery():
    """Show simple status"""
    try:
        processor = EmailProcessor("config/config.yaml")
        
        # Check for pending review
        pending = processor.get_pending_review()
        if pending:
            email_count = len(pending['emails'])
            run_id = pending['run'][0]
            print(f"📧 {email_count} emails ready for review (Run {run_id})")
            print(f"🌐 Review at: http://localhost:5000/review/{run_id}")
        else:
            print("✅ No emails pending review")
        
        # Check if can continue
        pagination_stats = processor.get_pagination_status()
        if pagination_stats['can_continue']:
            print("💡 Ready to analyze next page of emails")
        else:
            print("💡 Ready to start analyzing from beginning")
            
        return True
    except Exception as e:
        print(f"❌ Error checking status: {e}")
        return False

def delete_one_email():
    """Delete the first email from pending review (for testing)"""
    try:
        processor = EmailProcessor("config/config.yaml")
        
        # Get pending analysis
        pending = processor.get_pending_review()
        if not pending:
            print("No pending analysis found. Run 'python main.py --page' first.")
            return False
        
        emails = pending['emails']
        if not emails:
            print("No emails in pending analysis.")
            return False
        
        # Get first email details
        first_email = emails[0]
        email_id = first_email[2]  # email_id column
        subject = first_email[3]   # subject column  
        sender = first_email[4]    # sender column
        
        print(f"Testing deletion of:")
        print(f"Subject: {subject}")
        print(f"From: {sender}")
        
        # Confirm with user
        confirm = input("Delete this email? (y/n): ")
        if confirm.lower() != 'y':
            print("Deletion cancelled.")
            return False
        
        # Create decisions dict (delete first email, skip others)
        decisions = {email_id: 'delete'}
        
        # Execute deletion
        run_id = pending['run'][0]
        success = processor.execute_user_decisions(run_id, decisions)
        
        if success:
            print("✅ Email deleted successfully!")
            print("Check your Gmail trash folder to confirm.")
            return True
        else:
            print("❌ Deletion failed.")
            return False
            
    except Exception as e:
        print(f"Error: {e}")
        return False

def show_setup():
    """Show setup instructions"""
    print("""
SETUP INSTRUCTIONS
==================

1. Install dependencies:
   pip install -r requirements.txt

2. Get Groq API key:
   - Go to https://console.groq.com/
   - Create API key
   - Set environment variable: GROQ_API_KEY=your-key

3. Setup Gmail API:
   - Go to https://console.cloud.google.com/
   - Enable Gmail API
   - Download credentials.json to config/

4. Test connections:
   python main.py --test

5. Run analysis:
   python main.py --analyze
    """)

def main():
    parser = argparse.ArgumentParser(description='Simple Email Management Agent')
    
    parser.add_argument('--page', action='store_true', help='Analyze next 50 emails')
    parser.add_argument('--continue', dest='continue_flag', action='store_true', help='Continue from last page')
    parser.add_argument('--test', action='store_true', help='Test API connections')
    parser.add_argument('--setup', action='store_true', help='Show setup instructions')
    parser.add_argument('--stats', action='store_true', help='Show processing statistics')
    parser.add_argument('--status', action='store_true', help='Check current status')
    parser.add_argument('--delete-one', action='store_true', help='Delete one email for testing')
    
    args = parser.parse_args()
    
    if not any(vars(args).values()):
        parser.print_help()
        return
    
    if args.setup:
        show_setup()
    elif args.test:
        test_connections()
    elif args.stats:
        show_stats()
    elif args.status:
        check_recovery()
    elif args.delete_one:
        delete_one_email()
    elif args.page:
        run_paginated_analysis()
    elif args.continue_flag:
        continue_pagination()

if __name__ == '__main__':
    main() 
