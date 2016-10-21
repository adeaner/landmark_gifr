# Landmark Gifr

## Install
Install python dependencies:
```
pip install -r requirements.txt
```


## Usage

Great documentation can be found in the script's docs:
```
python gifr.py --help
```
Note: don't forget to add your API key to the top of the file.

** Que to Nate: Please open gifr.py. It has a feature list, usage, examples, and feature requests/TODOs. **

## Quick 'n Dirty Examples
### Statue of Liberty
Default ordering of images is to 'fly over' a point of interest. Flyover ordering is collecting images in a similar satAzimuth and sorting by offNadirAngle.
```
python gifr.py --coord="40.68924716076039, -74.04454171657562"
```
![](examples/statue_of_liberty.gif)

### Tokyo Skytree
The tallest structure in the world. Keeping offNadirAngle similar, the images are ordered by satAzimuth.
```
python gifr.py --coord="35.710139, 139.810833" --resolution=1.2 --order=panby
```
![](examples/tokyo_skytree.gif)

### DG
I already roughly filter out black (no data boundaries), flat grey, and too bright of images, but clouds and funkyness still comes through. A date stamp watermark is added to the GIF for order method = date.
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
