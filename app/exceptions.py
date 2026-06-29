class HotelBookingException(Exception):
    def __init__(self, errno, message):
        self.errno = errno
        self.message = message
        super().__init__(message)
