-- ====================================================================
-- CHƯƠNG II: DỮ LIỆU MẪU PHỤC VỤ KIỂM THỬ CÁC EDGE CASES
-- ====================================================================

-- Tắt kiểm tra khóa ngoại để dọn dẹp dữ liệu cũ (Reset trạng thái DB sạch)
SET FOREIGN_KEY_CHECKS = 0;
TRUNCATE TABLE HoaDon;
TRUNCATE TABLE DatPhong;
TRUNCATE TABLE KhachHang;
TRUNCATE TABLE Phong;
TRUNCATE TABLE LoaiPhong;
SET FOREIGN_KEY_CHECKS = 1;

-- 1. Thêm Loại Phòng (3 hạng phòng)
INSERT INTO LoaiPhong (TenLoai, GiaTieuChuan, SucChuaToiDa) VALUES
('Standard', 800000.00, 2),
('Deluxe', 1400000.00, 3),
('Suite', 3000000.00, 4);

-- 2. Thêm Phòng (6 phòng phân bổ đủ các trạng thái)
INSERT INTO Phong (TenPhong, Tang, MaLoaiPhong, TrangThai) VALUES
('101', 1, 1, 'Trong'),
('102', 1, 1, 'Trong'),
('201', 2, 2, 'Trong'),
('202', 2, 2, 'Dang_O'),
('301', 3, 3, 'Dang_Don_Dep'),
('302', 3, 3, 'Bao_Tri'); -- Phòng 302 dùng để kiểm tra bộ lọc ẩn bảo trì của Admin

-- 3. Thêm Khách Hàng mẫu
INSERT INTO KhachHang (HoTen, CCCD, DienThoai) VALUES
('Nguyễn Văn Khang', '079201012345', '0901234567'),
('Phan Minh Đức', '079201012346', '0901234568'),
('Lê Tuấn Đạt', '079201012347', '0901234569');

-- 4. Thêm Đơn Đặt Phòng (Để thử nghiệm xung đột lịch lưu trú và phạt cọc)
-- Đơn đặt 1: Đã cọc cho phòng 201 trong tương lai. Nếu tìm kiếm phòng trống chồng vào khoảng thời gian này, phòng 201 phải bị loại trừ mặc dù trạng thái vật lý của nó hiện tại vẫn là 'Trong'.
INSERT INTO DatPhong (MaKH, MaPhong, NgayCheckIn, NgayCheckOut, TienCoc, TrangThaiDon) VALUES
(1, 3, DATE_ADD(CURDATE(), INTERVAL 2 DAY), DATE_ADD(CURDATE(), INTERVAL 5 DAY), 200000.00, 'Da_Coc');

-- Đơn đặt 2: Đơn đã hủy
INSERT INTO DatPhong (MaKH, MaPhong, NgayCheckIn, NgayCheckOut, TienCoc, TrangThaiDon) VALUES
(2, 1, DATE_SUB(CURDATE(), INTERVAL 10 DAY), DATE_SUB(CURDATE(), INTERVAL 8 DAY), 0.00, 'Da_Huy');

-- Đơn đặt 3: Đơn đã hoàn thành (Dùng để kiểm thử Hóa đơn 1-1 và trigger)
INSERT INTO DatPhong (MaKH, MaPhong, NgayCheckIn, NgayCheckOut, TienCoc, TrangThaiDon) VALUES
(3, 5, DATE_SUB(CURDATE(), INTERVAL 3 DAY), DATE_SUB(CURDATE(), INTERVAL 1 DAY), 500000.00, 'Hoan_Thanh');

-- 5. Thêm Hóa Đơn tương ứng với Đơn đặt 3 (Đã hoàn thành)
INSERT INTO HoaDon (MaDatPhong, TienPhong, TienDichVu, TongTien) VALUES
(3, 6000000.00, 150000.00, 6150000.00);
