-- Task 2: Add education_system column and update values
ALTER TABLE temporal_metadata ADD COLUMN IF NOT EXISTS education_system VARCHAR(50);

-- Update education_system for specific documents
UPDATE temporal_metadata SET education_system='chinh_quy' WHERE document_number IN ('1393/QĐ-ĐHCNTT', '159/QĐ-ĐHCNTT', '354/QĐ-ĐHCNTT');
UPDATE temporal_metadata SET education_system='tien_tien' WHERE document_number = '1451/QĐ-ĐHCNTT';
