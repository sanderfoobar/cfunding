from uuid import uuid4

import PIL.ImageOps
from PIL import Image, ImageFilter
from quart import Quart, session, request, abort, Response
from captcha.image import ImageCaptcha
from quart import current_app as app

import settings


class FundingCaptcha(ImageCaptcha):
    # override for different colors
    def generate_image(self, chars):
        background = (255, 255, 255, 255)
        color = (155, 28, 46, 255)
        im = self.create_captcha_image(chars, color, background)
        self.create_noise_dots(im, color)
        self.create_noise_curve(im, color)
        im = im.filter(ImageFilter.SMOOTH)
        return im
