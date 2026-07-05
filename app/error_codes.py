# Ánh xạ mã lỗi định danh hệ thống (SQLSTATE/MYSQL_ERRNO -> UI Message)
ERROR_MESSAGES = {
    51001: "Ngày Check-out không hợp lệ (nhỏ hơn hoặc bằng Ngày Check-in).",
    51002: "Số tiền cọc hoặc chi phí phát sinh không hợp lệ (nhỏ hơn 0).",
    51003: "Không tìm thấy mã định danh đối tượng (Khách hàng/Phòng/Đơn đặt) trong hệ thống.",
    51004: "Chỉ được phép đặt phòng trước ít nhất 1 ngày.",
    52001: "Phòng không còn trống trong thời gian yêu cầu (Overbooking).",
    52002: "Trạng thái đơn đặt hiện tại không cho phép thực hiện hành động nghiệp vụ.",
    52003: "Phòng đang trong trạng thái bảo trì (Đã được khóa bởi lễ tân).",
    53001: "Lỗi đồng thời / Gặp hiện tượng Deadlock do tranh chấp tài nguyên dải chỉ mục.",
    53002: "Hết thời gian chờ (Lock Timeout) - Vui lòng thử lại sau.",
}

def get_error_message(errno, default_msg="Đã xảy ra lỗi không xác định hệ thống."):
    return ERROR_MESSAGES.get(errno, default_msg)
