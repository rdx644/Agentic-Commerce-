"""
Simulate a network timeout mid-payment.
Proves the 'one failure handled gracefully' requirement.

This script:
1. Creates a valid guardrail intent and passes the gate.
2. Dispatches a payment to Razorpay.
3. Intentionally corrupts our local ledger to simulate a timeout/dropped response.
4. Triggers the reconciliation service to detect the discrepancy and fix the ledger.
"""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database import init_db, get_db_transaction
from src.catalog import service as catalog_service
from src.guardrail.models import SpendIntent, CartItem, Decision
from src.guardrail import service as guardrail_service
from src.payment.models import PaymentDispatchRequest
from src.payment import service as payment_service
from src.payment import reconciliation

def main():
    print("=== Simulating Network Timeout & Reconciliation ===")
    
    # 1. Setup session and clear old state
    session_id = f"sim_fail_{int(time.time())}"
    print(f"\n[1] Starting session: {session_id}")
    
    manifest = catalog_service.get_manifest()
    target_item = manifest.items[0] # Pick the first item
    
    intent = SpendIntent(
        session_id=session_id,
        items=[CartItem(item_id=target_item.item_id, quantity=1)],
        stated_ceiling_paise=target_item.price_paise,
        catalog_hash=manifest.hash,
        actor="system",
        intent_type="checkout"
    )
    
    # 2. Pass Guardrail
    print(f"\n[2] Checking intent against guardrail...")
    decision = guardrail_service.check_spend(intent)
    if decision.decision != Decision.PASS:
        print(f"❌ Guardrail failed: {decision.reason}")
        return
        
    print(f"✅ Guardrail passed. Issued capability token: {decision.capability_token_id}")
    
    # 3. Dispatch Payment
    print(f"\n[3] Dispatching payment to Razorpay...")
    dispatch_req = PaymentDispatchRequest(
        session_id=session_id,
        capability_token=decision.capability_token,
        amount_paise=target_item.price_paise,
        currency="INR"
    )
    
    dispatch_resp = payment_service.dispatch_payment(dispatch_req)
    if not dispatch_resp.success:
        print(f"❌ Payment dispatch failed: {dispatch_resp.message}")
        print("Check if RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET are set in .env")
        return
        
    print(f"✅ Payment dispatched. Razorpay Order ID: {dispatch_resp.razorpay_order_id}")
    record_id = dispatch_resp.payment_record_id
    
    # 4. Simulate Failure (Corrupt Ledger)
    print(f"\n[4] 💥 SIMULATING NETWORK TIMEOUT 💥")
    print("Overwriting our local database status back to 'PENDING', as if we never received the response...")
    with get_db_transaction() as conn:
        conn.execute(
            "UPDATE payment_records SET status = 'PENDING' WHERE id = ?",
            (record_id,)
        )
        
    print("Local ledger status corrupted to 'PENDING'.")
    
    # 5. Trigger Reconciliation
    print(f"\n[5] Triggering Reconciliation Service...")
    print("The service will poll Razorpay as the source of truth.")
    
    result = reconciliation.reconcile_payment(record_id)
    
    print("\n=== Reconciliation Result ===")
    print(f"Original Local Status: PENDING")
    print(f"Razorpay Source of Truth: {result.razorpay_status}")
    print(f"Corrected Local Status: {result.local_status}")
    print(f"Action Taken: {result.action_taken}")
    
    if result.reconciled:
        print("\n✅ SUCCESS: The failure was handled gracefully and the ledger was corrected.")
    else:
        print("\n❌ FAILED: Reconciliation could not resolve the discrepancy.")

if __name__ == "__main__":
    main()
