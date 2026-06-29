-- ====================================================================
-- CHƯƠNG II: TRIGGER ĐỒNG BỘ TRẠNG THÁI VẬT LÝ
-- trg_CapNhatTrangThaiPhong: AFTER UPDATE ON DatPhong
-- ====================================================================

DELIMITER //

DROP TRIGGER IF EXISTS trg_CapNhatTrangThaiPhong//

CREATE TRIGGER trg_CapNhatTrangThaiPhong
AFTER UPDATE ON DatPhong
FOR EACH ROW
BEGIN
    -- Khi đơn đặt chuyển sang trạng thái Hoàn thành, tự động chuyển phòng sang 'Dang_Don_Dep'
    IF NEW.TrangThaiDon = 'Hoan_Thanh' AND OLD.TrangThaiDon <> 'Hoan_Thanh' THEN
        UPDATE Phong 
        SET TrangThai = 'Dang_Don_Dep' 
        WHERE MaPhong = NEW.MaPhong;
    END IF;
END//

DELIMITER ;
