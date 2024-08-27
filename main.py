#/bin/env python
import svgwrite, csv, requests
import xml.etree.ElementTree as ET
from io import BytesIO

class Sticker:
    def _parseColour(self, colour):
        r = int(colour[1:3],16)
        g = int(colour[3:5],16)
        b = int(colour[5:7],16)
        return svgwrite.utils.rgb(r,g,b,"RGB")


    def __init__(self,designation,name,allegiance,icon,flag,size):
        self.designation = designation
        self.name = name
        self.bgcolour = self._parseColour("#FFC0CB")
        self.allegiance = "neutral"
        if allegiance == "NATO":
            self.bgcolour = self._parseColour("#118ACB")
            self.allegiance = "friendly"
        if allegiance == "PACT":
            self.bgcolour = self._parseColour("#CC0000")
            self.allegiance = "hostile"
        if allegiance.startswith("UNK:"):
            self.bgcolour = self._parseColour(allegiance[4:11])
            self.allegiance = "unknown"
        if allegiance.startswith("CIV:"):
            self.bgcolour = self._parseColour("#AAFFAA")
            self.allegiance = "neutral"
        self.icon = icon
        self.flag = flag
        self.width = 20
        if size == "armour" or size == "small":
            self.width = 20
        if size == "medium":
            self.width = 30
        if size == "large":
            self.width = 40
        pass


    def makeSticker(self):
        self.sticker = svgwrite.Drawing(f"out/{self.designation}.svg",size=(f"{self.width}mm",f"8mm"))
        self.sticker.add(self.makeBackground())
        self.sticker.add(self.makeName())
        self.sticker.add(self.makeIcon())
        self.sticker.add(self.makeFlagBordered())
        self.sticker.add(self.makeDesignation())
        return self.sticker


    def makeBackground(self):
        return self.sticker.rect((0,0),(f"{self.width}mm",f"8mm"),0,0,stroke="none",fill=self.bgcolour)


    def makeName(self):
        style="font-size:12px;font-family:RobotoMono Nerd Font;text-anchor:middle;dominant-baseline:middle;"
        g = self.sticker.g(style=style)
        name = svgwrite.text.Text(self.name,(f"{self.width/2}mm","2.25mm"))
        g.add(name)
        return g


    def makeIcon(self):
        return svgwrite.image.Image(f"../icons/{self.icon}_{self.allegiance}.svg",("1mm","3mm"),width="4mm",height="4mm")


    def makeFlagBordered(self):
        tree = ET.parse(f"flags/{self.flag}.svg")
        w,h = tree.getroot().attrib["width"], tree.getroot().attrib["height"]
        ar = float(int(w))/float(int(h))
        rh = 1
        rw = 1
        if ar > 1:
            #wider
            rh = 1/ar
        else:
            #taller
            rw = 1/ar
        rx = (1-rw)*2
        ry = (1-rh)*2
        w = 4*rw
        h = 4*rh
        flag = svgwrite.image.Image(f"../flags/{self.flag}.svg",(f"{self.width-5}mm",f"{5-h/2}mm"),width=f"{w}mm",height=f"{h}mm")
        g = self.sticker.g()
        g.add(self.sticker.rect((f"{self.width-5+rx}mm",f"{3+ry}mm"),(f"{w}mm",f"{h}mm"),0,0,stroke="black",fill="none"))
        g.add(flag)
        return g
        


    def makeDesignation(self):
        style="font-size:14px;font-family:RobotoMono Nerd Font;text-anchor:middle;dominant-baseline:middle;"
        g = self.sticker.g(style=style)
        designation = svgwrite.text.Text(self.designation,(f"{self.width/2}mm","5.5mm"));
        g.add(designation)
        return g

    
def fromCSV(filename):
    with open(filename,"r") as f:
        reader = csv.reader(f, delimiter=",")
        for i, line in enumerate(reader):
            if i == 0:
                continue
            sticker = Sticker(line[0],line[1],line[2],line[3],line[4],line[5])
            sticker.makeSticker().save()


def main():
    fromCSV("input.csv")
    pass


if __name__ == "__main__":
    main()
