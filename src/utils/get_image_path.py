import os

def get_image_path(image_name: str) -> str:
    return os.path.join(os.path.dirname(__file__), '..', 'images', image_name)
