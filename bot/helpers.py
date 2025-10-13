# Helper utilities for bot commands

import re
import logging
from typing import Tuple, Optional

logger = logging.getLogger(__name__)

def validate_and_extract_command(text: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Validate command format: [from] pqf [quarter] [year] [product]
    from: internal/eksternal
    quarter: q1/q2/q3/q4
    year: 4-digit year
    product: robolabs/appcenter
    Returns: (from_value, product, error_message)
    """
    # Remove bot mention and clean text
    text = re.sub(r'<@[^>]+>', '', text).strip().lower()

    # Define validation patterns
    valid_froms = ['internal', 'eksternal']
    valid_products = ['agentlabs', 'appcenter']

    # Flexible pattern: find all required keywords in any order
    from_match = re.search(r'(internal|eksternal)', text)
    pqf_match = re.search(r'pqf', text)
    product_match = re.search(r'(agentlabs|appcenter)', text)

    if not (from_match and pqf_match and product_match):
        return None, None, "Format perintah tidak valid"

    from_value = from_match.group(1)
    product = product_match.group(1)

    # Additional validations
    if from_value not in valid_froms:
        return None, None, f"From harus 'internal' atau 'eksternal', bukan '{from_value}'"

    if product not in valid_products:
        return None, None, f"Product harus 'agentlabs' atau 'appcenter', bukan '{product}'"

    return from_value.capitalize(), product.capitalize(), None

def parse_slack_permalink(permalink: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Parse Slack permalink to extract channel and thread_ts.
    Example: https://.../archives/C09KQAF0GBA/p1759804695537539?thread_ts=1759804695.537539
    Returns: (channel_id, thread_ts)
    """
    match = re.search(r'/archives/([A-Z0-9]+)/p(\d+)', permalink)
    thread_ts = None
    channel_id = None
    if match:
        channel_id = match.group(1)
        # Convert p1759804695537539 to 1759804695.537539
        p_ts = match.group(2)
        if len(p_ts) > 10:
            thread_ts = f"{p_ts[:-6]}.{p_ts[-6:]}"
        else:
            thread_ts = p_ts
    # Try to get thread_ts from query param if available
    m2 = re.search(r'thread_ts=(\d+\.\d+)', permalink)
    if m2:
        thread_ts = m2.group(1)
    return channel_id, thread_ts

def get_sheet_name(from_value: str, product: str) -> str:
    """Get sheet name based on from_value and product."""
    return f"{from_value} {product}"

def prepare_thread_content(thread_data: dict) -> str:
    """Prepare thread content for analysis"""
    content = []
    
    # Add parent message
    parent = thread_data.get('parent_message', {})
    content.append("PARENT MESSAGE:")
    content.append(f"User ID: {parent.get('user', 'Unknown')}")
    content.append(f"Text: {parent.get('text', '')}")
    content.append("")
    
    # Add replies
    replies = thread_data.get('replies', [])
    if replies:
        content.append("REPLIES:")
        for i, reply in enumerate(replies, 1):
            content.append(f"{i}. User ID: {reply.get('user', 'Unknown')}")
            content.append(f"   Text: {reply.get('text', '')}")
            content.append("")
    
    # Add metadata
    content.append("METADATA:")
    content.append(f"Total messages: {thread_data.get('message_count', 0)}")
    content.append(f"Timestamp: {thread_data.get('timestamp', '')}")
    
    return "\n".join(content)

def parse_analysis_response(response_text: str) -> dict:
    """Parse LLM response"""
    import json
    try:
        # Clean the response text
        response_text = response_text.strip()
        
        # Try to extract JSON from the response
        if response_text.startswith('```json'):
            response_text = response_text[7:-3]
        elif response_text.startswith('```'):
            response_text = response_text[3:-3]
        
        # Parse JSON
        analysis = json.loads(response_text)
        
        # Validate required fields
        required_fields = ['type', 'product', 'fitur', 'description', 'role', 'reporter', 'responder', 'severity', 'urgency']
        for field in required_fields:
            if field not in analysis:
                if field == 'severity':
                    analysis[field] = 'Others (Ask)'
                elif field == 'urgency':
                    analysis[field] = 'Low'
                else:
                    analysis[field] = 'Unknown'
        
        return analysis
        
    except json.JSONDecodeError as e:
        logger.error(f"Error parsing LLM response as JSON: {str(e)}")
        
        # Fallback
        return {
            'type': 'Other',
            'product': 'Unknown',
            'fitur': 'Unknown',
            'description': 'Gagal menganalisis thread',
            'role': 'Other',
            'reporter': 'Unknown',
            'responder': 'Unknown',
            'severity': 'Others (Ask)',
            'urgency': 'Low'
        }
    
    except Exception as e:
        logger.error(f"Error parsing analysis response: {str(e)}")
        return {
            'type': 'Other',
            'product': 'Unknown',
            'fitur': 'Unknown',
            'description': 'Error dalam analisis',
            'role': 'Other',
            'reporter': 'Unknown',
            'responder': 'Unknown',
            'severity': 'Others (Ask)',
            'urgency': 'Low'
        }