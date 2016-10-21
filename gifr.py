"""
Landmark Gifr

By: Ashley Deaner
For: Hackathon October 2016

Create a gif of a feature by simply providing point coordinates.
Features
    -   Ordering methods
    -   DigitalGlobe logo watermark for marketing, ex. Instagram
    -   debugging watermarks of IDAHO image id and timestamp
    -   throws out chips that are black, too grey, or bright white. Black and flat grey pixels are from boarder no data
        values.
    -   Selects highest res imagery if there are too many of chips.
    -   Creates a repeating looped GIF.

Usage:
    gifr.py --coord=COORD
    gifr.py --coord=COORD [--resolution=RESOLUTION] [--width=WIDTH] [--order=ORDER] [-v | --verbose]

Options:
    --coord=COORD               Latitude and Longitude in decimal degrees. Ex. 40.68924716076039, -74.04454171657562
    --width=WIDTH               Width/ height of square image. Doubling the width quadruples the speed and
                                file size [default: 512]
    --resolution=RESOLUTION     Pixel resolution. I recommend leaving width alone for speed and adjusting resolution for
                                zoom level [default: 0.3]
    --order=ORDER               ordering method. [default: flyover]
                                flyover: Fly over landmark. Recommended for tall structures
                                panby: Pan past landmarkk. Recommended for tall structures
                                seasons: ordered by month/day. Not recommended for tall structures
                                date: ordered by date. Not recommended for tall structures at high resolution
    --verbose
    -h --help

Examples:
    python gifr.py --coord="40.68924716076039, -74.04454171657562"                      # Statue of Liberty
    python gifr.py --coord="35.710139, 139.810833" --resolution=1.2 --order=panby       # Tokyo Skytree
    python gifr.py --coord="39.912419, -105.001847" --resolution=0.6  --order=date      # DG
    python gifr.py --coord="-33.857043, 151.215173" --resolution=0.6 --order=panby      # Sydney Opera House
    python gifr.py --coord="48.858222, 2.2945" --resolution=1.2 --order=panby           # Eiffel Tower
    python gifr.py --coord="32.896944, -97.038056" --order=date --resolution=1.2        # Dallas Airport
    python gifr.py --coord="-22.948611, -43.157222" --resolution=1.2 --order=date       # Sugarloaf Mountain
    python gifr.py --coord="25.197139, 55.274111" --resolution=2.4 --order=panby        # Burj Khalifa, UAE
    python gifr.py --coord="41.866091, -87.617014" --resolution=5 --order=date          # Field Museum, zoomed out
    python gifr.py --coord="41.890168, 12.492380" --resolution=1.2 --order=panby        # Colosseum
    python gifr.py --coord="-22.951944, -43.210556" --resolution=0.6 --order=panby      # Christ the Redeemer statue

Feature Requests/ TODO:
- season ordering methods
- auto registration - image to image registration GBDX Task
- histogram equalization
- expose as a GBDX task / API
- filepath

"""
import json
import logging
import os
import time
from StringIO import StringIO

import imageio
import numpy as np
import requests
from PIL import Image, ImageStat, ImageDraw, ImageFont
from dateutil import parser
from docopt import docopt

global lat
global lon

# TODO: DON'T CHECK IN WITH TOKEN
access_token = None

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s: %(funcName)s: %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S")


def catalog_search(lat, lon):
    """
    Search the GBDX Catalog for IDAHO imagery

    :param lat: decimal latitude
    :param lon: decimal longitude
    :return: JSON search results
    """
    point = "{lon} {lat}".format(lon=lon, lat=lat)

    search = {
        "searchAreaWkt": "POLYGON (({point}, {point}, {point}, {point}, {point}))".format(point=point),
        "filters": ["cloudCover < 80"],
        "types": ["IDAHOImage"]
    }

    def __search(search):

        header = {"Authorization": "Bearer {}".format(access_token),
                  "Content-Type": "application/json"}
        result = requests.post("https://geobigdata.io/catalog/v1/search", headers=header, data=json.dumps(search))

        if not len(result.json()["results"]) > 0:
            raise ValueError("No catalog results found for {0}, {1}".format(lat, lon))

        return result.json()

    result = __search(search)

    # reduce results by increasing cloud cover
    if len(result["results"]) > 50:
        search["filters"] = ["cloudCover < 50"]
        result = __search(search)

    # reduce results by using only WV03
    if len(result["results"]) > 50:
        search["filters"] = ["cloudCover < 20", "sensorPlatformName = 'WV03'"]
        result = __search(search)

    logging.debug("Catalog search returned {} records".format(len(result["results"])))

    return result


def parse_search(search_result):
    """
    Pair multispectral and panchromatic images and include sorting properties.

    :param search_result: JSON search result
    :return: [[multispectral IDAHO id, panchromatic IDAHO id, offNadirAngle, satAzimuth],[]]
    """
    pairs = dict()

    for result in search_result["results"]:
        vdi = result["properties"]["vendorDatasetIdentifier"]

        # add vdi to pair list of it does not exist
        if vdi not in pairs:
            pairs[vdi] = [None] * 6

        # fill in sets
        if result["properties"]["sensorName"] == "Panchromatic":
            # assume off nadir angle already set, just fill in pan id
            pairs[vdi][1] = result["identifier"]
        else:
            # assume sensors besides pan will work (8 band and 4 band)
            pairs[vdi][0] = result["identifier"]
            # fill in off nadir angle
            pairs[vdi][2] = result["properties"]["offNadirAngle"]
            pairs[vdi][3] = result["properties"]["satAzimuth"]
            pairs[vdi][4] = result["properties"]["sensorPlatformName"]
            pairs[vdi][5] = parser.parse(result["properties"]["acquisitionDate"])

    # pop elements if list is not populated and strip vdi
    list_pairs = []
    for key, value in pairs.iteritems():
        if None not in value:
            list_pairs.append(value)

    logging.info("Collected {} image pairs".format(len(list_pairs)))

    return list_pairs


def order_images(pairs, method):
    """
    ordering methods:
    flyover - similar quadrant, ordered by off nadir angle
    panby - similar nadir angle, ordered by azimuth
    seasons - ordered by month/day
    date - ordered by date

    :param pairs:
    :return: ordered pairs
    """

    def __collect_similar(pairs, index):

        if len(pairs) > 10:
            if index == 3:
                # azimuth bins
                bins = np.linspace(0, 360, 7)
            elif index == 2:
                # off nadir bins
                bins = np.linspace(0, 90, 7)
            import collections
            images_in_bins = collections.defaultdict(list)
            for val in pairs:
                images_in_bins[int(np.digitize(val[index], bins))].append(val)

            similar = max(images_in_bins.values(), key=len)
            return similar
        else:
            # don't trim too hard
            return pairs

    def __trim_number_of_pairs(pairs):
        # if there is alot of images still, just keep WV sats
        if len(pairs) > 10:
            filtered_pairs = filter(lambda e: e[4] in ["WV02", "WV03"], pairs)
            if len(filtered_pairs) >= 5:
                pairs = filtered_pairs
        if len(pairs) > 10:
            filtered_pairs = filter(lambda e: e[4] in ["WV03"], pairs)
            if len(filtered_pairs) >= 5:
                pairs = filtered_pairs
        return pairs

    if method == "flyover":
        similar = __collect_similar(pairs, 3)  # similar azimuth
        trimmed = __trim_number_of_pairs(similar)
        ordered_pairs = sorted(trimmed, key=lambda x: float(x[2]))  # ordered by off nadir angle
    elif method == "panby":
        similar = __collect_similar(pairs, 2)  # similar off nadir angle
        trimmed = __trim_number_of_pairs(similar)
        ordered_pairs = sorted(trimmed, key=lambda x: float(x[3]))  # ordered by azimuth
    elif method == "date":
        similar = __collect_similar(pairs, 2)  # similar off nadir angle
        similar = __collect_similar(similar, 3)  # similar off nadir angle
        trimmed = __trim_number_of_pairs(similar)
        ordered_pairs = sorted(trimmed, key=lambda x: x[5])

    else:
        raise (ValueError, "Order method not found")

    logging.info("Using the {0} best chips for {1} order method".format(len(ordered_pairs), method))
    return ordered_pairs


def get_chip(image_ids, width=512, resolution=0.3, debug=False, method=None):
    """
    Get an IDAHO/IPE image chip
    :param image_ids: set of IDAHO ids for multi and pan images
    :return: a PIL PNG image in numpy array format
    """

    # IDAHO/IPE TMS Chipper
    # http://gbdxdocs.digitalglobe.com/v1/docs/get-tms-tile
    bucket_name = 'idaho-images'
    idaho_id_multi = image_ids[0]
    idaho_id_pan = image_ids[1]
    # width = 512
    height = width
    bands = '2,1,0'
    url = 'http://idaho.geobigdata.io/v1/chip/centroid/{bucket_name}/{idaho_id_multi}?' \
          'lat={lat}&long={long}&panId={idaho_id_pan}' \
          '&bands={bands}&doDRA=true&brightness=1' \
          '&width={width}&height={height}&resolution={resolution}' \
          '&token={access_token}'.format(bucket_name=bucket_name, idaho_id_multi=idaho_id_multi,
                                         idaho_id_pan=idaho_id_pan,
                                         lat=lat, long=lon, bands=bands,
                                         width=width, height=height, resolution=resolution,
                                         access_token=access_token)
    try:
        response = requests.get(url)

        image = Image.open(StringIO(response.content))
        image.load()
        image_palette = image.convert("RGB")

        logging.info("Got chip: {}".format(str(idaho_id_multi)))

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
        for x in range(0, width, int(width / 100)):
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
            draw.text((20, 20), idaho_id_multi, (255, 255, 255), font=font)
        # watermark timestamp
        if method == "date":
            draw.text((20, width - 20), image_ids[5].strftime("%Y-%m-%dT%H:%M:%S.%fZ"), (255, 255, 255), font=font)

        layer = Image.new('RGBA', image_palette.size, (0, 0, 0, 0))
        watermark = Image.open("dglogo-whiteonly-std.png")

        # scale, but preserve the aspect ratio
        ratio = min(
            float(image_palette.size[0]) / watermark.size[0], float(image_palette.size[1]) / watermark.size[1])
        w = int(watermark.size[0] * ratio) / 4
        h = int(watermark.size[1] * ratio) / 4
        watermark = watermark.resize((w, h))

        layer.paste(watermark, ((width - w) - 20, 20))
        watermarked_image = Image.composite(layer, image_palette, layer)

        return watermarked_image

    except Exception as e:
        logging.error("Something bad happened: {}".format(e))
        return None


def stack_chips(pairs, width, resolution, debug, method):
    """
    Get all the image chips

    :param pairs: IDAHO image ids
    :param width: pass chip width from cmd line into TMS chipper
    :return: a list of PIL PNG images
    """
    images = []
    count = 1
    for pair in pairs:
        logging.info("Getting chip {0} out of {1}...".format(count, len(pairs)))
        count += 1
        chip = get_chip(pair, width, resolution, debug, method)
        # skip None's
        if chip is not None:
            images.append(chip)

    logging.info("Number of unique chips in GIF: {}".format(len(images)))
    return images


def fade_images(images):
    """
    Insert faded image for transitions.

    :param images:
    :return:
    """
    images_w_fade = []
    images_w_fade.append(images[0])

    for i in range(0, len(images) - 1):
        blended = Image.blend(images[i], images[i + 1], alpha=0.5)
        images_w_fade.append(blended)
        images_w_fade.append(images[i + 1])

    return images_w_fade


def create_gif(images):
    """
    Create the GIF!

    :param images: list of PIL PNGs
    :return: None
    """

    # Convert from PIL to numpy array
    image_np = []
    for image in images:
        image_np.append(np.array(image))

    dur = [0.1] * len(images)
    for i in range(0, len(images), 4):
        dur[i] = 0.5

    kargs = {'duration': dur}
    imageio.mimsave('my.gif', image_np, **kargs)


if __name__ == "__main__":
    arguments = docopt(__doc__)

    tic = time.time()

    # set default values for lat long
    latlong = arguments["--coord"]
    latlong_dict = latlong.split(", ")
    lat = latlong_dict[0]
    lon = latlong_dict[1]

    width = int(arguments["--width"])
    resolution = float(arguments["--resolution"])
    method = arguments["--order"]
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

    results_json = catalog_search(lat, lon)

    id_pairs = parse_search(results_json)

    ordered_id_pairs = order_images(id_pairs, method)

    images = stack_chips(ordered_id_pairs, width, resolution, verbose, method)

    images_with_fade = fade_images(fade_images(images))  # fade twice

    reversed_images = list(reversed(images_with_fade[1:-1]))

    create_gif(images_with_fade + reversed_images)

    toc = time.time()

    logging.info("Landmark Gifr took {} seconds".format(toc - tic))
