"""
Amendment chain SQL patches for 790 -> 1393 -> 507 (tu xa chain).
Applied via docker exec psql on 2026-05-23.
Do NOT re-run without checking current state first.

Prerequisite: 507/QD-DHCNTT must have education_system='tu_xa' (verified from 04-03).

Patch 1: 1393 amends 790
  UPDATE temporal_metadata SET amends_documents = '["790/QD-DHCNTT"]'::jsonb
  WHERE document_number = '1393/QD-DHCNTT'
    AND (amends_documents IS NULL OR amends_documents = '[]'::jsonb);

Patch 2: 790 amended_by 1393
  UPDATE temporal_metadata SET amended_by_documents = '["1393/QD-DHCNTT"]'::jsonb
  WHERE document_number = '790/QD-DHCNTT'
    AND (amended_by_documents IS NULL OR amended_by_documents = '[]'::jsonb);

Patch 3: 507 amends 1393 (SKIPPED -- 507 already had amends_documents=["1206/QD-DHCNTT"])
  UPDATE temporal_metadata SET amends_documents = '["1393/QD-DHCNTT"]'::jsonb
  WHERE document_number = '507/QD-DHCNTT'
    AND (amends_documents IS NULL OR amends_documents = '[]'::jsonb);

Patch 4: 1393 amended_by 507
  UPDATE temporal_metadata
  SET amended_by_documents = COALESCE(amended_by_documents, '[]'::jsonb) || '["507/QD-DHCNTT"]'::jsonb
  WHERE document_number = '1393/QD-DHCNTT'
    AND NOT (COALESCE(amended_by_documents, '[]'::jsonb) @> '["507/QD-DHCNTT"]'::jsonb);

Final state verified (2026-05-23):
  790/QD-DHCNTT: amends_documents=null, amended_by_documents=["1393/QD-DHCNTT"]
  1393/QD-DHCNTT: amends_documents=["790/QD-DHCNTT"], amended_by_documents=["507/QD-DHCNTT"]
  507/QD-DHCNTT: amends_documents=["1206/QD-DHCNTT"] (pre-existing; Patch 3 WHERE guard skipped)
"""

CHAIN = ["790/QĐ-ĐHCNTT", "1393/QĐ-ĐHCNTT", "507/QĐ-ĐHCNTT"]
EDUCATION_SYSTEM = "tu_xa"
STATUS = "applied"
