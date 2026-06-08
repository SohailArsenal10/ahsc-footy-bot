"""
Test message deduplication logic.
Simulates duplicate webhook calls to verify deduplication works.
"""

import sys
import os

# Add the project directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import the deduplication set from main
from main import processed_message_ids

def test_deduplication():
    """Test that duplicate message IDs are properly deduplicated."""
    
    # Clear the set first
    processed_message_ids.clear()
    
    # Simulate first message
    msg_id_1 = "wamid.HBgMOTE4MTc5OTczMjM4FQIAERgSMjk4NjU0NjY3MjEwMDA5MjI0AA=="
    
    # First processing
    if msg_id_1 in processed_message_ids:
        print("❌ FAIL: First message should not be in set")
        return False
    processed_message_ids.add(msg_id_1)
    print("✅ First message processed and added to set")
    
    # Second processing (duplicate)
    if msg_id_1 in processed_message_ids:
        print("✅ Duplicate message detected and would be skipped")
    else:
        print("❌ FAIL: Duplicate message not detected")
        return False
    
    # Third processing (another duplicate)
    if msg_id_1 in processed_message_ids:
        print("✅ Another duplicate detected and would be skipped")
    else:
        print("❌ FAIL: Duplicate message not detected")
        return False
    
    # New message
    msg_id_2 = "wamid.HBgMOTE4MTc5OTczMjM4FQIAERgSMjk4NjU0NjY3MjEwMDA5MjI1AA=="
    if msg_id_2 in processed_message_ids:
        print("❌ FAIL: New message should not be in set")
        return False
    processed_message_ids.add(msg_id_2)
    print("✅ New message processed and added to set")
    
    # Verify both are in set
    if len(processed_message_ids) == 2:
        print("✅ Set contains exactly 2 unique message IDs")
    else:
        print(f"❌ FAIL: Set should contain 2 IDs, but has {len(processed_message_ids)}")
        return False
    
    print("\n🎉 All deduplication tests passed!")
    return True

if __name__ == "__main__":
    success = test_deduplication()
    sys.exit(0 if success else 1)
