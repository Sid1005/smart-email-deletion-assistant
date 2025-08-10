from groq import Groq
import json
from datetime import datetime
import os

class GroqAnalyzer:
    def __init__(self, api_key=None, model="llama-3.1-8b-instant"):
        # Use environment variable if no API key provided
        self.api_key = api_key or os.getenv('GROQ_API_KEY')
        if not self.api_key:
            raise ValueError("GROQ_API_KEY environment variable is required")
        
        self.client = Groq(api_key=self.api_key)
        self.model = model
    
    def analyze_emails(self, emails, deletion_rules):
        """Analyze emails and provide deletion recommendations"""
        
        # Prepare email data for analysis (limit to avoid token limits)
        email_summaries = []
        for email in emails[:30]:  # Analyze in smaller batches for Groq
            email_summaries.append({
                'id': email['id'],
                'subject': email['subject'],
                'sender': email['sender'],
                'snippet': email['snippet'][:150],  # Shorter snippets
                'is_unread': email['is_unread'],
                'date': email['date']
            })
        
        prompt = self._create_analysis_prompt(email_summaries, deletion_rules)
        
        try:
            # Use Groq chat completion
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert email management assistant. Analyze emails and provide JSON recommendations for deletion."
                    },
                    {
                        "role": "user", 
                        "content": prompt
                    }
                ],
                temperature=0.3,  # Lower temperature for more consistent results
                max_tokens=4000,
                top_p=0.9,
                stream=False,  # Don't stream for JSON parsing
                stop=None
            )
            
            # Get the response
            response_text = completion.choices[0].message.content
            
            # Parse the response
            analysis = self._parse_analysis_response(response_text)
            print("Groq analysis completed")
            return analysis
            
        except Exception as error:
            print(f'Error analyzing emails with Groq: {error}')
            return self._create_fallback_analysis(emails)
    
    def _create_analysis_prompt(self, emails, rules):
        """Create prompt for email analysis"""
        protected_senders = rules.get('protected_senders', [])
        auto_delete_patterns = rules.get('auto_delete_patterns', [])
        
        return f"""You are an email management assistant. Analyze these emails and categorize them for potential deletion.

PROTECTED SENDERS (NEVER DELETE): {protected_senders}
AUTO-DELETE PATTERNS: {auto_delete_patterns}

EMAILS TO ANALYZE:
{json.dumps(emails, indent=2)}

Provide your recommendation in this EXACT JSON format (no other text):

{{
  "analysis": {{
    "email_id": {{
      "action": "delete|review|keep",
      "category": "promotional|newsletter|notification|personal|work|other",
      "confidence": 0.0-1.0,
      "reason": "Brief explanation"
    }}
  }},
  "summary": {{
    "total_emails": number,
    "recommended_deletions": number,
    "needs_review": number,
    "keep": number
  }}
}}

RULES:
1. NEVER recommend deleting emails from protected senders
2. Be conservative - when in doubt, mark for review
3. Consider email age, sender reputation, content type
4. Unread emails need more careful consideration
5. Personal emails should typically be kept
6. Marketing/promotional emails are usually safe to delete
7. Mark anything suspicious or important as "review"

RESPOND ONLY WITH VALID JSON - NO OTHER TEXT."""

    def _parse_analysis_response(self, response_text):
        """Parse Groq's JSON response"""
        try:
            # Clean up the response
            response_text = response_text.strip()
            
            # Remove markdown code blocks if present
            if response_text.startswith('```json'):
                response_text = response_text[7:-3]
            elif response_text.startswith('```'):
                response_text = response_text[3:-3]
            
            # Parse JSON
            analysis = json.loads(response_text)
            
            # Validate structure
            if 'analysis' not in analysis or 'summary' not in analysis:
                raise ValueError("Invalid analysis structure")
            
            return analysis
            
        except json.JSONDecodeError as e:
            print(f"Error parsing Groq JSON response: {e}")
            print(f"Raw response (first 500 chars): {response_text[:500]}...")
            return None
        except Exception as e:
            print(f"Error processing Groq response: {e}")
            return None
    
    def _create_fallback_analysis(self, emails):
        """Create basic analysis if Groq fails"""
        analysis = {
            "analysis": {},
            "summary": {
                "total_emails": len(emails),
                "recommended_deletions": 0,
                "needs_review": len(emails),
                "keep": 0
            }
        }
        
        # Mark all emails for review as fallback
        for email in emails:
            analysis["analysis"][email['id']] = {
                "action": "review",
                "category": "other",
                "confidence": 0.5,
                "reason": "Fallback - requires manual review"
            }
        
        return analysis
    
    def generate_daily_summary(self, emails, analysis):
        """Generate a human-readable daily summary"""
        summary = analysis.get('summary', {})
        
        # Categorize emails by action
        delete_emails = []
        review_emails = []
        keep_emails = []
        
        for email in emails:
            email_analysis = analysis['analysis'].get(email['id'])
            if email_analysis:
                if email_analysis['action'] == 'delete':
                    delete_emails.append((email, email_analysis))
                elif email_analysis['action'] == 'review':
                    review_emails.append((email, email_analysis))
                else:
                    keep_emails.append((email, email_analysis))
        
        # Create readable summary
        summary_text = f"""
DAILY EMAIL ANALYSIS REPORT
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Powered by: Groq AI ({self.model})

SUMMARY:
- Total emails analyzed: {summary.get('total_emails', 0)}
- Recommended for deletion: {summary.get('recommended_deletions', 0)}
- Flagged for review: {summary.get('needs_review', 0)}
- Recommended to keep: {summary.get('keep', 0)}

RECOMMENDED FOR DELETION ({len(delete_emails)} emails):
"""
        
        for email, analysis_data in delete_emails[:10]:  # Show first 10
            summary_text += f"• {email['subject'][:60]}... (from: {email['sender'][:30]})\n"
            summary_text += f"  Reason: {analysis_data['reason']}\n"
        
        if len(delete_emails) > 10:
            summary_text += f"• ... and {len(delete_emails) - 10} more\n"
        
        summary_text += f"\nFLAGGED FOR REVIEW ({len(review_emails)} emails):\n"
        
        for email, analysis_data in review_emails[:5]:  # Show first 5
            summary_text += f"• {email['subject'][:60]}... (from: {email['sender'][:30]})\n"
            summary_text += f"  Reason: {analysis_data['reason']}\n"
        
        return {
            'text': summary_text,
            'delete_emails': delete_emails,
            'review_emails': review_emails,
            'keep_emails': keep_emails
        }

    def test_connection(self):
        """Test if Groq API is working"""
        try:
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": "Say 'Groq API connected successfully' and nothing else."
                    }
                ],
                max_tokens=50,
                temperature=0
            )
            
            message_content = completion.choices[0].message.content
            response = message_content.strip() if message_content else "No response"
            print(f"Groq API test: {response}")
            return True
            
        except Exception as e:
            print(f" Groq API test failed: {e}")
            return False 
