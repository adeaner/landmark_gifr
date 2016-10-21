# Landmark Gifr

Create a gif of a feature by simply providing point coordinates.

** Que to Nate: Please open gifr.py. It has a feature list, usage, examples, and feature requests/TODOs. **

## Easy Peazy Install
Install python dependencies:
```
pip install -r requirements.txt
```

## Simple Command Line Usage

Great documentation can be found in the script's docs:
```
python gifr.py --help
```
Note: don't forget to add your API key to the top of the file.

## Quick 'n Dirty Examples
### Statue of Liberty
Default ordering of images is to 'fly over' a point of interest. Flyover ordering is collecting images in a similar satAzimuth and sorting by offNadirAngle.
```
python gifr.py --coord="40.68924716076039, -74.04454171657562"
```
![](examples/statue_of_liberty.gif)

### Tokyo Skytree
The tallest structure in the world. Keeping offNadirAngle similar, the images are ordered by satAzimuth. See the plane?!
```
python gifr.py --coord="35.710139, 139.810833" --resolution=1.2 --order=panby
```
![](examples/tokyo_skytree.gif)

### DG
I roughly filter out black (no data boundaries), flat grey, and too bright of images, but clouds and funkyness still come through. A date stamp watermark is added to the GIF when order method = date.
```
python gifr.py --coord="39.912419, -105.001847" --resolution=0.6  --order=date
```
![](examples/dg_hq.gif)

### Sydney Opera House
```
python gifr.py --coord="-33.857043, 151.215173" --resolution=0.6 --order=panby
```
![](examples/sydney_opera_house.gif)

### Chicago's Field Museum
Zoomed out example.
```
python gifr.py --coord="41.866091, -87.617014" --resolution=5 --order=date
```
![](examples/field_museum.gif)

# THANK YOU!!

I'm in Austin this weekend for the Formula 1 race  :D
```
python gifr.py "--coord=30.134990, -97.634526" --resolution=5 --order=date
```
![](examples/circuit_of_the_americas.gif)
