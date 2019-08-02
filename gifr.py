"""
Landmark Gifr

By: Ashley Deaner
For: Hackathon October 2016
     Hackathon August 2019

Create a gif of a feature by simply providing point coordinates.
Features
    -   Requests images from RDA
    -   Parameterized ordering methods
    -   DigitalGlobe logo watermark for marketing, ex. Instagram
    -   Throws out chips that are black, too grey, or bright white. Black and flat grey pixels are from boarder no data
        values.
    -   Selects highest res imagery if there are too many of chips.
    -   Creates a repeating looped GIF.

Usage:
    gifr.py --coord=COORD
    gifr.py --coord=COORD [--width=WIDTH] [--order=ORDER] [-v | --verbose]

Options:
    --coord=COORD               Latitude and Longitude in decimal degrees. Ex. 40.68924716076039, -74.04454171657562
    --width=WIDTH               Width/ height of square image. Doubling the width quadruples the speed and
                                file size [default: 512]
    --gsd=GSD                   Pixel GSD. I recommend leaving width alone for speed and adjusting gsd for
                                zoom level [default: 0.3]
    --order=ORDER               ordering method. [default: flyover]
                                flyover: Fly over landmark. Recommended for tall structures
                                panby: Pan past landmarkk. Recommended for tall structures
                                seasons: ordered by month/day. Not recommended for tall structures
                                date: ordered by date. Not recommended for tall structures at high resolution
    --verbose
    -h --help

Examples:
    python gifr.py --coord="40.68924716076039, -74.04454171657562"               # Statue of Liberty
    python gifr.py --coord="35.710139, 139.810833" --gsd=1.2 --order=panby       # Tokyo Skytree
    python gifr.py --coord="39.912419, -105.001847" --gsd=0.6  --order=date      # DG
    python gifr.py --coord="-33.857043, 151.215173" --gsd=0.6 --order=panby      # Sydney Opera House
    python gifr.py --coord="48.858222, 2.2945" --gsd=1.2 --order=panby           # Eiffel Tower
    python gifr.py --coord="32.896944, -97.038056" --gsd=1.2 --order=date        # Dallas Airport
    python gifr.py --coord="-22.948611, -43.157222" --gsd=1.2 --order=date       # Sugarloaf Mountain
    python gifr.py --coord="25.197139, 55.274111" --gsd=2.4 --order=panby        # Burj Khalifa, UAE
    python gifr.py --coord="41.866091, -87.617014" --gsd=5 --order=date          # Field Museum, zoomed out
    python gifr.py --coord="41.890168, 12.492380" --gsd=1.2 --order=panby        # Colosseum
    python gifr.py --coord="-22.951944, -43.210556" --gsd=0.6 --order=panby      # Christ the Redeemer statue

Feature Requests:
- season ordering methods
- auto registration - image to image registration GBDX Task
- histogram equalization
- expose as a GBDX task / API
- filepath

"""
import collections
import json
import logging
import os
import time
from io import BytesIO

import imageio
import numpy as np
import requests
from PIL import Image, ImageStat, ImageDraw, ImageFont
from docopt import docopt
from gbdx_auth import gbdx_auth

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s: %(funcName)s: %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S")

global access_token


class Gifr:

    def __init__(self, lat, lon, tile_size, order):
        self.lat = lat
        self.lon = lon
        self.tile_size = tile_size
        self.order = order

        self.results = self.catalog_search()
        self.order_images()

        self.images = self.stack_chips()

        # fade twice
        self.fade_images()
        self.fade_images()

        # make a loop
        self.images = self.images + list(reversed(self.images[1:-1]))

        self.create_gif()

    def catalog_search(self):
        """
        Search the GBDX Catalog for IDAHO imagery

        :return: JSON search results
        """
        point = "{lon} {lat}".format(lon=self.lon, lat=self.lat)

        search = {
            "searchAreaWkt": "POLYGON (({point}, {point}, {point}, {point}, {point}))".format(point=point),
            "filters": ["cloudCover < 80", "sensorName LIKE Multispectral"],
            "types": ["IDAHOImage"]
        }

        def __search(body):

            header = {"Authorization": "Bearer {}".format(access_token),
                      "Content-Type": "application/json"}
            response = requests.post("https://geobigdata.io/catalog/v2/search", headers=header, data=json.dumps(body))

            if not len(response.json()["results"]) > 0:
                raise ValueError("No catalog results found for {0}, {1}".format(self.lat, self.lon))

            return response.json()

        results = __search(search)["results"]

        # deduplicate catalog ids
        unique_catalog_ids = []
        unique_results = []
        for i in range(0, len(results) - 1):
            if results[i]["properties"]["catalogID"] not in unique_catalog_ids:
                unique_catalog_ids.append(results[i]["properties"]["catalogID"])
                unique_results.append(results[i])
        results = unique_results

        # reduce results by increasing cloud cover
        if len(results) > 50:
            search["filters"] = ["cloudCover < 50"]
            results = __search(search)

        # reduce results by using only WV03
        if len(results) > 50:
            search["filters"] = ["cloudCover < 20", "sensorPlatformName = 'WV03'"]
            results = __search(search)

        logging.debug("Catalog search returned {} records".format(len(results)))

        return results

    def order_images(self):
        """
        ordering methods:
        flyover - similar quadrant, ordered by off nadir angle
        panby - similar nadir angle, ordered by azimuth
        seasons - ordered by month/day
        date - ordered by date
        """

        def __collect_similar(results, index):

            if len(results) > 10:
                bins = None
                if index == "satAzimuth":
                    # azimuth bins
                    bins = np.linspace(0, 360, 7)
                elif index == "offNadir":
                    # off nadir bins
                    bins = np.linspace(0, 90, 7)
                images_in_bins = collections.defaultdict(list)
                for val in results:
                    images_in_bins[int(np.digitize(val["properties"][index], bins))].append(val)

                return max(images_in_bins.values(), key=len)
            else:
                # don't trim too hard
                return results

        def __trim_number_of_pairs(results):
            # if there is a lot of images still, just keep WV sats
            if len(results) > 10:
                filtered_results = list(filter(lambda e: e["properties"]["sensorPlatformName"] in
                                                          ["WORLDVIEW02_VNIR", "WORLDVIEW03_VNIR"], results))
                if len(filtered_results) >= 5:
                    results = filtered_results
            if len(results) > 10:
                filtered_results = list(filter(lambda e: e["properties"]["sensorPlatformName"] in
                                                          ["WORLDVIEW03_VNIR"], results))
                if len(filtered_results) >= 5:
                    results = filtered_results
            return results

        if self.order == "flyover":
            similar = __collect_similar(self.results, "satAzimuth")  # similar azimuth
            trimmed = __trim_number_of_pairs(similar)
            self.results = sorted(trimmed, key=lambda x: float(x["properties"]["offNadirAngle"]))
        elif self.order == "panby":
            similar = __collect_similar(self.results, "offNadirAngle")
            trimmed = __trim_number_of_pairs(similar)
            self.results = sorted(trimmed, key=lambda x: float(x["properties"]["satAzimuth"]))
        elif self.order == "date":
            similar = __collect_similar(self.results, "offNadirAngle")
            similar = __collect_similar(similar, "satAzimuth")
            trimmed = __trim_number_of_pairs(similar)
            self.results = sorted(trimmed, key=lambda x: x["properties"]["acquisitionDate"])

        else:
            raise (ValueError, "Order method not found")

        logging.info("Using the {0} best chips for {1} order method".format(len(self.results), self.order))

    @staticmethod
    def get_chip(catalog_id, date, lat, lon, tile_size, x_translate, y_translate, debug=False, method=None):
        """
        Get an IDAHO/IPE image chip
        :return: a PIL PNG image in numpy array format
        """

        # IDAHO/IPE TMS Chipper
        # http://gbdxdocs.digitalglobe.com/v1/docs/get-tms-tile

        try:
            url_point = 'https://ughlicoordinatesapi.geobigdata.io/v2/reproject'
            body ={"source": {"crs": "EPSG:4326", "geometry": "POINT({lon} {lat})".format(lat=lat, lon=lon)}, "destination": {"crs":"EPSG:32645"}}
            response_point = requests.post(url_point, data=json.dumps(body),
                                           headers={"Accept": "application/json",
                                                    "Content-Type": "application/json"})

            point = json.loads(response_point.content).get("geometry")
            m_lon = point.split(" (")[1].split(" ")[0]
            m_lat = point.split(" ")[-1].split(")")[0]

            url = 'https://rda-api-v2-alpha.geobigdata.io/v2/template/' \
                  '8cbd4d8e194f10a365476578023d08834debe65e71c7477ce8f2a98139c9d7a2' \
                  '/webtile/0/0?' \
                  'p=catalogId={catalog_id}' \
                  '&p=draType=RADIOMETRICDRA' \
                  '&p=crs=EPSG:32645' \
                  '&p=correctionType=Acomp' \
                  '&p=bands=Pansharp' \
                  '&p=destAT=%5B0.5, 0, 0, -0.5, {lon}, {lat}%5D' \
                  '&p=bandSelection=RGB' \
                  '&nodeid=TileSize' \
                  '&p=tileSize={tile_size}' \
                  '&p=xtranslate={x_translate}' \
                  '&p=ytranslate={y_translate}'.format(catalog_id=catalog_id,
                                                     lat=m_lat, lon=m_lon, tile_size=tile_size,
                                                     x_translate=x_translate, y_translate=y_translate)

            response = requests.get(url, headers={"Accept": "image/png",
                                                  "Authorization": "Bearer " + access_token})

            image = Image.open(BytesIO(response.content))
            image.load()
            image_palette = image.convert("RGB")

            logging.info("Got chip: {}".format(str(catalog_id)))

            # check for bright chips
            # http://stackoverflow.com/questions/3490727/what-are-some-methods-to-analyze-image-brightness-using-python
            image_l = image.convert("L")
            stat = ImageStat.Stat(image_l)
            logging.debug("Mean brightness: {}".format(stat.mean[0]))
            if stat.mean[0] > 220:
                logging.debug("bright image thrown out")
                return None
            elif stat.mean[0] < 45:
                logging.debug("black or grey image thrown out")
                return None
            else:
                pass

            # check for black chips
            count = 0
            # tic = time.time()
            pixels = image_palette.load()
            for x in range(0, tile_size, int(tile_size / 100)):
                c_pixel = pixels[x, x]
                if c_pixel == (0, 0, 0):
                    count += 1
            # print("sample pixels took {} seconds".format(time.time() - tic))
            logging.debug("Number of sampled black pixels: {}".format(count))

            if count < 10:
                # image_palette.show()
                pass
            else:
                logging.debug("black chip thrown out")
                return None

            draw = ImageDraw.Draw(image_palette)
            font = ImageFont.truetype("/Library/Fonts/Arial Bold.ttf", 16)
            # watermark idaho image id
            if debug:
                draw.text((20, 20), catalog_id, (255, 255, 255), font=font)
            # watermark timestamp
            if method == "date":
                draw.text((20, tile_size - 20), date.strftime("%Y-%m-%dT%H:%M:%S.%fZ"), (255, 255, 255), font=font)

            layer = Image.new('RGBA', image_palette.size, (0, 0, 0, 0))
            # watermark = Image.open("dglogo-whiteonly-std.png")
            watermark = Image.open("maxar_green_logo.jpg")

            # scale, but preserve the aspect ratio
            ratio = min(
                float(image_palette.size[0]) / watermark.size[0], float(image_palette.size[1]) / watermark.size[1])
            w = int(watermark.size[0] * ratio / 4)
            h = int(watermark.size[1] * ratio / 4)
            watermark = watermark.resize((w, h))

            layer.paste(watermark, ((tile_size - w) - 20, 20))
            watermarked_image = Image.composite(layer, image_palette, layer)

            return watermarked_image

        except Exception as e:
            logging.error("Something bad happened: {}".format(e))
            return None

    def stack_chips(self):
        """
        Get all the image chips

        :return: a list of PIL PNG images
        """

        offsets = json.load(open("offsets.json"))
        images = []
        count = 1
        for result in self.results:
            logging.info("Getting chip {0} out of {1}...".format(count, len(self.results)))
            count += 1
            catalog_id = result["properties"]["catalogID"]
            x_translate = 0.0
            y_translate = 0.0
            if catalog_id in offsets:
                x_translate = offsets.get(catalog_id).get("xtranslate")
                y_translate = offsets.get(catalog_id).get("ytranslate")
            chip = self.get_chip(catalog_id,
                                 result["properties"]["acquisitionDate"], self.lat, self.lon, self.tile_size,
                                 x_translate, y_translate)
            # skip None's
            if chip is not None:
                images.append(chip)

        logging.info("Number of unique chips in GIF: {}".format(len(images)))
        return images

    def fade_images(self):
        """
        Insert faded image for transitions.
        """

        images_w_fade = [self.images[0]]

        for i in range(0, len(self.images) - 1):
            blended = Image.blend(self.images[i], self.images[i + 1], alpha=0.5)
            images_w_fade.append(blended)
            images_w_fade.append(self.images[i + 1])

        self.images = images_w_fade

    def create_gif(self):
        """
        Create the GIF!
        """

        # Convert from PIL to numpy array
        image_np = []
        for image in self.images:
            image_np.append(np.array(image))

        dur = [0.1] * len(self.images)
        for i in range(0, len(self.images), 4):
            dur[i] = 0.5

        kargs = {'duration': dur}
        imageio.mimsave('my.gif', image_np, **kargs)


if __name__ == "__main__":
    arguments = docopt(__doc__)

    tic = time.time()

    latlong = arguments["--coord"].split(", ")
    verbose = arguments["--verbose"] or arguments["-v"]

    # Setup logging
    logger = logging.getLogger()
    logger.addHandler(logging.NullHandler())
    logging.getLogger("requests").setLevel(logging.WARNING)
    if verbose:
        logger.setLevel(logging.DEBUG)

    # Cleanup old gif
    try:
        os.remove("my.gif")
    except OSError:
        pass

    access_token = gbdx_auth.get_session().access_token

    Gifr(float(latlong[0]), float(latlong[1]), int(arguments["--width"]), arguments["--order"])

    toc = time.time()

    logging.info("Landmark Gifr took {} seconds".format(toc - tic))
