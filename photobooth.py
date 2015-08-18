#! /usr/bin/python

import picamera
import pygame
import atexit
import io
import os
import time
import multiprocessing
import threading
import sys
import re
import errno

IDLE, TAKING_PICS, SHOWING_PIC = range(3)
global state
state = IDLE
PIC_DELAY = 3 # time in secs to delay
SHOW_TIME = 5 # time in secs to show photo
NO_OF_PICS = 3 # number of pics on each strip
xSize, ySize = 640, 400
# global tmp array for low quality streaming
rgb = bytearray(xSize * ySize * 4)
# [ img resolution, size of output, field of view ]
sizeData =  [(1440, 1080), (xSize, ySize), (0.0, 0.0, 1.0, 1.0)]
imageDir = "images/"

def mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as exc: # Python >2.5
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else: raise

def getNextDirName(topPath):
    prefix = "images_"
    f = []
    for (dirpath, dirnames, filenames) in os.walk(topPath):
        f.extend(dirnames)
        break
    max_val = 0;
    for dirname in f:
        matches = map(int, re.findall(r'\d+', dirname))
        if len(matches) != 0:
            if max_val < matches[0]:
                max_val = matches[0]
    max_val = max_val+1
    return prefix + str(max_val)

def readImgFromCamera(camera):
    stream = io.BytesIO() # Capture into in-memory stream
    camera.capture(stream, use_video_port=True, format='rgba')
    stream.seek(0)
    stream.readinto(rgb)
    stream.close()
    img = pygame.image.frombuffer(rgb[0: (xSize * ySize * 4)], sizeData[1], 'RGBA')
    return img

def takePicFromCamera(camera, filename):
    '''
    Save a jpeg to a file from picamera
    '''
    oldRes = camera.resolution
    camera.resolution = (2592, 1944) # set to max resolution
    camera.capture(filename, use_video_port=False, format='jpeg', thumbnail=None)
    camera.resolution = oldRes

def createBMPforPrinting(filenames, destfile):
    '''
    Creates a 6" by 2" bmp file for printing
    Note: need to rotate images so they facing right way
    '''
    if len(filenames) != NO_OF_PICS:
        print "Error: need " + str(NO_OF_PICS) + " images to create photostrip"
        return
    # 6" width, 2" height
    printXSize, printYSize = 1832, 614
    margin = 50
    topBuf = 60
    marginY = 10
    header = pygame.image.load(imageDir + 'makerHeader.png', 'png')
    header = pygame.transform.rotate(header, 90)
    bmpSurface = pygame.Surface((printXSize, printYSize))
    bmpSurface.fill((0,0,0)) # fill with black
    bmpSurface.blit(header, (topBuf, (printYSize - header.get_height()) / 2))
    imgXSize = printYSize - 2*marginY
    imgYSize = int(round(imgXSize*3.0/4.0)) # maintain the aspect ratio
    xLoc = header.get_width() + 2*topBuf
    for i in range(NO_OF_PICS):
        img = pygame.image.load(filenames[i], 'jpg')
        img = pygame.transform.scale(img, (imgXSize, imgYSize));
        img = pygame.transform.rotate(img, 90)
        bmpSurface.blit(img, (xLoc, marginY))
        xLoc += imgYSize + margin

    # save the bmp file for printing
    pygame.image.save(bmpSurface, destfile)
    bmpSurface = pygame.transform.rotate(bmpSurface, -90)
    newWidth = int(round(float(ySize)*(float(printYSize)/float(printXSize))))
    bmpSurface = pygame.transform.scale(bmpSurface, (newWidth, ySize))
    # return the surface to be displayed
    return bmpSurface
    
def addTextOnTop(screen, filename):
    img = pygame.image.load(filename, 'png')
    screen.blit(img, ((xSize - img.get_width() ) / 2, (ySize - img.get_height()) / 2))

def photoboothLoop(gpio_pin):
    #    os.seteuid(1000) # give up root for photobooth
    global state
    # INIT CAMERA
    camera = picamera.PiCamera()
    atexit.register(camera.close)
    camera.vflip = False
    camera.hflip = False
    camera.brightness = 60
    camera.resolution = sizeData[1]
    camera.crop       = (0.0, 0.0, 1.0, 1.0) # can focus in for narrower field of view

    # BUILD A SCREEN
    os.environ["SDL_FBDEV"] = "/dev/fb0"
    pygame.init()
    pygame.mouse.set_visible(False)
    screen = pygame.display.set_mode((xSize,ySize))

    darken = False
    exitNow = False

    picCount = 0
    lastPicTime = 0
    filenames = []
    dirname = "/media/disk/Photobooth_images/"
    newDir = dirname
    imgToShow = readImgFromCamera(camera)
    img = imgToShow
    nextState = IDLE

    while True:
        if state == IDLE:
            img = readImgFromCamera(camera)
            screen.blit(img, ((xSize - img.get_width() ) / 2, (ySize - img.get_height()) / 2))

            for event in pygame.event.get():
                if event.type == pygame.KEYDOWN:
                    keyEvent = event
                    if event.key == pygame.K_ESCAPE:
                        exitNow = True
                    if event.key == pygame.K_SPACE:
                        state = TAKING_PICS
                        lastPicTime = time.clock()
                        filenames = []
                        nextState = IDLE
                        picCount = 0
            #      os.seteuid(0)
            if not RPIO.input(gpio_pin):
                state = TAKING_PICS
                lastPicTime = time.clock()
                filenames = []
                nextState = IDLE
                newDir = dirname + getNextDirName(dirname)
                mkdir_p(newDir)
                picCount = 0
            #    os.seteuid(1000)

        elif state == TAKING_PICS:
            if time.clock() - PIC_DELAY > lastPicTime or picCount + 1 > NO_OF_PICS:
                picCount += 1
                if picCount > NO_OF_PICS:
                    picCount = 0
                    screen.blit(img, ((xSize - img.get_width() ) / 2, (ySize - img.get_height()) / 2))
                    addTextOnTop(screen, imageDir + 'preparing.png')
                    pygame.display.update()
                    imgToShow = createBMPforPrinting(filenames, newDir + '/' + "photostrip.bmp")
                    filenames = []
                    nextState = IDLE
                    state = SHOWING_PIC
                else:
                    screen.blit(img, ((xSize - img.get_width() ) / 2, (ySize - img.get_height()) / 2))
                    addTextOnTop(screen, imageDir + 'saving.png')
                    pygame.display.update()
                    filename = newDir + "/" + 'image' + str(picCount) + '.jpeg'
                    takePicFromCamera(camera, filename)
                    filenames.append(filename)
                lastPicTime = time.clock()
            else:
                img = readImgFromCamera(camera)
                screen.blit(img, ((xSize - img.get_width() ) / 2, (ySize - img.get_height()) / 2))
                if time.clock() - PIC_DELAY + 1 > lastPicTime:
                    addTextOnTop(screen, imageDir + '1img.png')
                elif time.clock() - PIC_DELAY + 2 > lastPicTime:
                    addTextOnTop(screen, imageDir + '2img.png')
                elif time.clock() - PIC_DELAY + 3 > lastPicTime:
                    addTextOnTop(screen, imageDir + '3img.png')
                elif time.clock() - PIC_DELAY + 4 > lastPicTime:
                    addTextOnTop(screen, imageDir + '4img.png')
                elif time.clock() - PIC_DELAY + 5 > lastPicTime:
                    addTextOnTop(screen, imageDir + '5img.png')
        elif state == SHOWING_PIC:
            if time.clock() - SHOW_TIME > lastPicTime:
                lastPicTime = time.clock()
                state = nextState
                nextState = IDLE
            else:
                screen.fill((0,0,0))
                screen.blit(imgToShow, ( 0, 0) ) # (xSize - imgToShow.get_width() ) / 2, (ySize - imgToShow.get_height()) / 2))
                img = pygame.image.load(imageDir + 'printing_3.png', 'png')
                screen.blit(img, ((xSize - img.get_width() ), (ySize - img.get_height())))
        else:
            print "UNKNOWN STATE! back to IDLE"
            state = IDLE

        pygame.display.update()

        if(exitNow):
            break

if __name__ == "__main__":
    if os.getuid() != 0:
        print 'This must be run as root'
        sys.exit(1)
    
    gpio_pin = 4

    import RPIO
    RPIO.setup(gpio_pin, RPIO.IN, pull_up_down=RPIO.PUD_UP)

    photoboothLoop(gpio_pin)


