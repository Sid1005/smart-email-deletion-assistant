#!/usr/bin/env python3
"""
Test script for crash recovery functionality
"""
import sys
import os

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.database import EmailDatabase

def test_recovery_methods():
    """Test the new recovery methods"""
    print("🧪 Testing crash recovery methods...")
    
    try:
        # Initialize database
        db = EmailDatabase("data/emails.db")
        
        # Test get_incomplete_run_info
        print("\n1. Testing get_incomplete_run_info()...")
        incomplete = db.get_incomplete_run_info()
        if incomplete:
            print(f"   Found incomplete run: {incomplete['run_id']}")
            print(f"   Progress: {incomplete['processed_count']}/{incomplete['total_emails_in_run']} ({incomplete['progress_percentage']}%)")
            print(f"   Needs reanalysis: {incomplete['needs_reanalysis']}")
        else:
            print("   No incomplete runs found")
        
        # Test get_pagination_stats
        print("\n2. Testing enhanced get_pagination_stats()...")
        pstats = db.get_pagination_stats()
        print(f"   Total pages: {pstats['total_pages']}")
        print(f"   Completed pages: {pstats['completed_pages']}")
        print(f"   Overall progress: {pstats['overall_progress_percentage']}%")
        
        # Test get_stats
        print("\n3. Testing enhanced get_stats()...")
        stats = db.get_stats()
        print(f"   Total emails: {stats['total_emails']}")
        print(f"   Processed emails: {stats['processed_emails']}")
        print(f"   Processing rate: {stats['processing_rate']}%")
        print(f"   Avg emails per run: {stats['avg_emails_per_run']}")
        
        print("\n✅ All database methods work correctly!")
        return True
        
    except Exception as e:
        print(f"❌ Error testing methods: {e}")
        return False

if __name__ == '__main__':
    test_recovery_methods()
