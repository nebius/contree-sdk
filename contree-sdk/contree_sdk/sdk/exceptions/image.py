class ContreeImageNotFound(Exception):
    def __init__(self, image: str):
        self.image = image
        super().__init__(f"Image '{image}' not found")
