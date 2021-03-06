#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import time
import random
import re
import quantum780_operation as qdoperation
import switchconfig_operation as switchconfig
import telnet_operation as telnet
import logger as log
import terminalcolor as tcolor
import write2dashboard
from optparse import OptionParser
from datetime import datetime
#log.disable(log.logger.info) #disable log

BASEDIR = os.path.dirname(os.path.abspath(__file__))
#BASEDIR = "C:\\Simon\\CrickTest"
SWITCHCONFIG = BASEDIR+"\\ConfigResolutionData.xlsx"
INPCOUNT = 0 #count input protocal pass number
OUTPCOUNT = 0 #count output protocal pass number
INFCOUNT = 0 #count input protocal fail number
OUTFCOUNT = 0 #count output protocal fail number
PATPCOUNT = 0 #count output pattern pass number
PATFCOUNT = 0 #count output pattern fail number
logname = BASEDIR+"\\log\\" + time.strftime("%Y%m%d_%H%M%S") + ".log"
log = log.Logger(logname)

def executeTest(cmdoptions, cmdargs):
    """
    Execute the test;
    :param cmdoptions:
    :param cmdargs:
    :return:
    """
    global INPCOUNT, OUTPCOUNT,INFCOUNT,OUTFCOUNT, PATPCOUNT, PATFCOUNT, TESTPARAS, outport, outporttype
    print("Your Test will be start after 3 seconds, please wait...")
    loadProcess()
    #Get config vars from the data sheet:
    config_d = switchconfig.SwitchConfigOperation(SWITCHCONFIG, 1).load_config()
    log.logger.info(config_d)
    filename = BASEDIR+"\\"+config_d['ConfigFilePath']
    edidfile = BASEDIR+"\\"+config_d['EdidFilePath']
    log.logger.info(cmdoptions)
    tn = telnet.TelnetApp(config_d['MasterIP'],config_d['MasterUsername'],config_d['MasterPassword'])
    log.logger.info("switch_ip:"+config_d['SwitchIP']+"switch_username:"+config_d['SwitchUsername']+"Switch_pwd:" \
              +config_d['SwitchPassword'])
    swcregconf = switchconfig.SwitchConfigOperation(filename, 0)
    swcolorconfig = switchconfig.SwitchConfigOperation(filename, 2)
    qd = qdoperation.Quantum780Operation()
    inportdic = initPort(config_d['InputPortType'])
    log.logger.info("The input port type is:%s."% inportdic)
    outportdic = initPort(config_d['OutputPortType'])
    log.logger.info("The output port type is:%s."% outportdic)
    repetitions = int(cmdoptions.repetitions)
    ar = cmdoptions.aspectratio
    incolor = cmdoptions.colorspace
    outcolor = cmdoptions.outcolorspace
    if 'YCbCr444'==outcolor:
        outputcolor = 'YUV444'
    else: outputcolor = outcolor
    aspectratio = cmdoptions.aspectratio
    patterntest = cmdoptions.patterntest
    #hdcpout = cmdoptions.hdcpout
    hdcpin = cmdoptions.hdcpin
    hdcpdut = cmdoptions.hdcpdut
    #initialize the port;
    outport = config_d['SutDPS'].split(":")[1]
    #Test Step:
    #Initialize QD generator, default:1080p
    log.logger.info("Start initialize Quantum Data!")
    qd.sent_qd_generator('1080p60', cmdoptions.patternname, \
                         cmdoptions.colorspace, \
                         cmdoptions.deepcolor, \
                         cmdoptions.outport, \
                         cmdoptions.hdcpout)
    qd.switch_hpformats('0') #disable hotplug formats
    #Initialize SUT default input and output
    log.logger.info("Start initialize DUT in/out port!")
    inport = inportdic['HDMI1']
    inporttype = 'HDMI1'
    outport = outportdic['HDMI1']
    outporttype = 'HDMI1'
    cmd_dut = ''.join('ci' + inportdic['HDMI1'] + 'o' + outportdic['HDMI1'])
    # Set Switch output
    switchport = "".join(re.findall(r"\d", outporttype))
    cmd_sw = ''.join('ci' + switchport + 'oall')
    tn.send_thor_cmd(config_d['SutDPS'], cmd_dut)
    tn.send_thor_cmd(config_d['SwitchDPS'], cmd_sw)
    # Initial RX HDCP to follow
    tn.send_thor_cmd(config_d['SutDPS'], 'VIDOUT_HDCP-FOLLOW')
    log.logger.info("Hey,Testing Start......")
    # Execute repetions
    while(repetitions):
        for qdcode in getTimingList(swcregconf, cmdoptions.timing, 37):
            log.logger.info("The current input timing is %s" % qdcode)
            # Get the input code to get h,v
            incode= swcregconf.getTimingExpect(qdcode)
            #Set input timing
            qd.sent_qd_generator(qdcode)
            #Set Dut switch paraeters, paser "--random";
            if cmdoptions.random != None:
                time.sleep(int(cmdoptions.interval))
                cmd_dut,cmd_sw, outport, outporttype, inporttype = randSwitchPort(cmdoptions.random, inportdic, outportdic)
                log.logger.info("The input port is %s" % inporttype)
                log.logger.info("The output port is %s" % outporttype)
                #Check if input port support HDBT Big 4K
                if isHdbtSupport(cmdoptions, qdcode, inporttype):
                    pass
                else:
                    continue
                #input support
                log.logger.info("Switch the DUT port is: %s" % cmd_dut)
                tn.send_thor_cmd(config_d['SutDPS'], cmd_dut)
                log.logger.info("Switch the Switch port is: %s" % cmd_sw)
                tn.send_thor_cmd(config_d['SwitchDPS'], cmd_sw)
            # Config hdcp, if duthdcp was not follow, then execute hdcpdut, or hdcpin
            if hdcpdut != 'follow':
                if 'None' == hdcpdut:
                    tn.send_thor_cmd(config_d['SutDPS'], 'VIDOUT_HDCP-NO HDCP')
                elif '14' == hdcpdut:
                    tn.send_thor_cmd(config_d['SutDPS'], 'VIDOUT_HDCP-HDCP1.4')
                elif '22' == hdcpdut:
                    tn.send_thor_cmd(config_d['SutDPS'], 'VIDOUT_HDCP-HDCP2.2')
                else:
                    raise ("Unknow hdcp ICSP command parameters!")
            else:
                configHDCP(qd, hdcpin)
            #Set scaler mode
            if 'auto'== cmdoptions.scaletiming: #or 'random'==cmdoptions.scaletiming:
                log.logger.info("The auto scaler mode is %s" % cmdoptions.scaletiming)
                for scalercode in getTimingList(swcregconf, cmdoptions.scaletiming, 38):
                    #HDBT can not support 4096x2160@50/60 YCbCr/RGB input or output
                    if isHdbtSupport(cmdoptions, scalercode, outporttype):
                        pass
                    else:
                        continue
                    log.logger.info("Set Scaler Out timing to %s!" % scalercode)
                    # set scaler to auto
                    if cmdoptions.random != 'None':
                        newdps = config_d['SutDPS'].replace(":1:", ":" + outport + ":")
                        log.logger.info("The new SUT DPS is %s" % newdps)
                        tn.send_thor_cmd(newdps, 'vidout_scale-auto')
                    else:
                        newdps = config_d['SutDPS']
                        tn.send_thor_cmd(newdps, 'vidout_scale-auto')
                    #Set aspect Ratio
                    arcmd='vidout_aspect_ratio-'+ar
                    tn.send_thor_cmd(newdps, arcmd)
                    log.logger.info("Set aspectratio to %s !" % ar)
                    #set output colorspace
                    cscmd = 'vidout_color_space-'+outputcolor
                    tn.send_thor_cmd(newdps, cscmd)
                    log.logger.info("Set output colorspace to %s !" % outcolor)
                    outcode = swcregconf.getTimingExpect(scalercode)
                    # set qd input port
                    log.logger.info("Set QD analyze port!")
                    setQdInputport(qd, outporttype)
                    # write edid
                    writeEdid(swcregconf, scalercode, edidfile, qd)
                    #check pattern
                    if checkPattern(qd, qdcode, scalercode, incode, outcode, patterntest, incolor, outcolor, swcolorconfig,
                                     colorimetry='auto'):
                            PATPCOUNT=PATPCOUNT+1
                    else:PATFCOUNT=PATFCOUNT+1
            else:
                log.logger.info("The manual scaler mode is %s" % cmdoptions.scaletiming)
                #scalercode = cmdoptions.scaletiming
                for scalercode in getTimingList(swcregconf, cmdoptions.scaletiming, 38):
                    # HDBT can not support 4096x2160@50/60 YCbCr/RGB input or output
                    if isHdbtSupport(cmdoptions, scalercode, outporttype):
                        pass
                    else:
                        continue
                    log.logger.info("Set Scaler Out timing to %s!" % scalercode)
                    # set scaler to manual
                    if cmdoptions.random != 'None':
                        #config_d['SutDPS'] = config_d['SutDPS'].replace(":1:", ":" + outport + ":") need know why not?
                        newdps = config_d['SutDPS'].replace(":1:", ":" + outport + ":")
                        log.logger.info("The new SUT DPS is %s" % newdps)
                        #tn.send_thor_cmd(config_d['SutDPS'], 'vidout_scale-manual')
                        tn.send_thor_cmd(newdps, 'vidout_scale-manual')
                    else:
                        newdps = config_d['SutDPS']
                        tn.send_thor_cmd(newdps, 'vidout_scale-manual')
                    #"for"  set aspect Ratio
                    arcmd='vidout_aspect_ratio-'+ar
                    tn.send_thor_cmd(newdps, arcmd)
                    log.logger.info("Set aspectratio to %s !" % ar)
                    #set output colorspac
                    cscmd = 'vidout_color_space-'+outputcolor
                    tn.send_thor_cmd(newdps, cscmd)
                    log.logger.info("Set output colorspace to %s !" % outcolor)
                    # set scaler output timing
                    outcode = swcregconf.getTimingExpect(scalercode)
                    cmd=''.join('VIDOUT_RES_REF-'+outcode['HRES']+'x'+outcode['VRES']+','+str(round(float(outcode['VRAT']))))
                    log.logger.info("The manual scaler timing out is %s" % cmd)
                    tn.send_thor_cmd(newdps, cmd)
                    #Set pattern test pattern
                    pcmd = 'vidout_testpat-' + patterntest
                    tn.send_thor_cmd(newdps, pcmd)
                    log.logger.info("The %s pattern test!"% patterntest)
                    #Set QD input port
                    log.logger.info("Set QD analyze port!")
                    setQdInputport(qd, outporttype)
                    #Check pattern
                    if checkPattern(qd, qdcode, scalercode, incode, outcode, patterntest, incolor, outcolor, swcolorconfig,
                                     colorimetry='auto'):
                        PATPCOUNT=PATPCOUNT+1
                    else:PATFCOUNT=PATFCOUNT+1
        repetitions = repetitions-1
    #Calculate all test result
    log.logger.info("OK,All Test Completed! Total: %d "%(INPCOUNT+INFCOUNT+OUTPCOUNT+OUTFCOUNT+PATPCOUNT+PATFCOUNT)+" cases, %d"\
                    %(INPCOUNT+OUTPCOUNT+PATPCOUNT)+" is PASS, %d" %(INFCOUNT+OUTFCOUNT+PATFCOUNT)+" is FAIL!")
    log.logger.info("INPUT Timing RESULT:%d"%(INPCOUNT)+" is PASS, %d"%(INFCOUNT)+" is FAIL. "\
                    "OUTPUT Timing RESULT: %d"%(OUTPCOUNT)+" is PASS, %d"%(OUTFCOUNT)+" is FAIL."\
                    "PATTERN TEST RESULT: %d"%(PATPCOUNT)+" is PASS, %d"%(PATFCOUNT)+" is FAIL.")
    totalnumber = INPCOUNT+INFCOUNT+OUTPCOUNT+OUTFCOUNT+PATPCOUNT+PATFCOUNT
    passnumber = INPCOUNT+OUTPCOUNT+PATPCOUNT
    failnumber = INFCOUNT+OUTFCOUNT+PATFCOUNT
    notrunnumber = totalnumber-passnumber-failnumber
    return passnumber, failnumber, notrunnumber

def initPort(porttype):
    """
    Initalize the DUT port
    :param porttype:
    :return: a port dic
    """
    dic = {}
    portlist = porttype.split(',')
    for opt in portlist:
        dic[opt.split(':')[0]] = opt.split(':')[1]
    return dic

def isHdbtSupport(cmdoptions, qdcode, porttype):
    if 'HDBT' in porttype:
        if qdcode == '2160p50w' or qdcode == '2160p60w':
            if cmdoptions.colorspace == 'RGB' or cmdoptions.colorspace == 'YCbCr444':
                log.logger.info("HDBT "+porttype+" can not support 4096x2160@50/60,RGB/YCbCr444!!!")
                return False
    return True

def configHDCP(qd, hdcpin):
    """
    Config DUT output hdcp or Set sink hdcp in
    :param qd:
    :param hdcpin:
    :return:
    """
    if hdcpin !='follow':
        if 'None' == hdcpin:
            qd.hdcp_alyzSwitch('0')
        elif '14' == hdcpin:
            qd.hdcp_alyzSwitch('1')
        elif '22' == hdcpin:
            qd.hdcp_alyzSwitch('2')
        else:
            raise ("Unknow Quantum hdcp key!")

def setQdInputport(qd, outporttype):
    """
    Set Quantum input analyzer port
    :param qd:
    :param outporttype:
    :return:
    """
    if 'HDMI' in outporttype:
        qd.set_input_signal(0)
    elif 'HDBT' in outporttype:
        qd.set_input_signal(1)
    else:raise("Quantum only support HDMI/HDBT this port type, please check your config file")

def getTimingList(swconfig, timingmode, col):
    if 'all' == timingmode or 'auto' == timingmode or 'manual' == timingmode:
        return swconfig.getSupportTimingCode(col)
    elif 'random' == timingmode:
        return random.choice(swconfig.getSupportTimingCode(col)).split()
    else:
        return timingmode.split()

def checkPattern(qd, qdincode, qdoutcode, incode, outcode, patterntest, incolor, outcolor, swcolorconfig, colorimetry='auto'):
    """

    :param qd: Quantum obj
    :param incode: input paras dic
    :param outcode: output paras dic
    :param patterntest: RED, GREEN, BLUE
    :param incolor: input colorspace
    :param outcolor: output colorspace
    :param swColorConfig: get colorspace expect paras
    :param colorimetry: set colorimetry under YCbCr mode(Auto BT601, BT709, BT2020)
    :return: Boolean
    """
    expect_input = incode
    expect_output = outcode
    # check outcode
    h = int(expect_output['HRES'])  # output hres
    v = int(expect_output['VRES'])  # output vres
    #if 4K, 4K capture was not support by 780E
    if '2160p50' in qdincode or '2160p60' in qdincode:
        if '2160p50' in qdoutcode or '2160p60' in qdoutcode:
            log.logger.info("Both In/Out are 4K")
            res = calculatePixel(1, 1, qd, h, v, incolor, outcolor, swcolorconfig, patterntest)
            if res:
                tcolor.cprint('Pattern Test was PASS', 'GREEN')
                log.logger.info("Pattern Test was PASS!")
                return True
            else:
                tcolor.cprint('Pattern Test was FAIL', 'RED')
                log.logger.info("Pattern Test was FAIL!")
                return False
        else:
            log.logger.info("In is 4K, Out not 4K")
            res = calculatePixel(1, 0, qd, h,v, incolor, outcolor, swcolorconfig, patterntest)
            if res:
                tcolor.cprint('Pattern Test was PASS','GREEN')
                log.logger.info("Pattern Test was PASS!")
                return True
            else:
                tcolor.cprint('Pattern Test was FAIL', 'RED')
                log.logger.info("Pattern Test was FAIL!")
                return False
    else:
        if '2160p50' in qdoutcode or '2160p60' in qdoutcode:
            log.logger.info("In not 4K, Out is 4K")
            res = calculatePixel(0, 1, qd, h ,v, incolor, outcolor, swcolorconfig, patterntest)
            if res:
                tcolor.cprint('Pattern Test was PASS', 'GREEN')
                log.logger.info("Pattern Test was PASS!")
                return True
            else:
                tcolor.cprint('Pattern Test was FAIL', 'RED')
                log.logger.info("Pattern Test was FAIL!")
                return False
        else:
            log.logger.info("Both are not 4K")
            res = calculatePixel(0, 0, qd, h, v, incolor, outcolor, swcolorconfig, patterntest)
            if res:
                tcolor.cprint('Pattern Test was Pass', 'GREEN')
                log.logger.info("Pattern Test was PASS!")
                return True
            else:
                tcolor.cprint('Pattern Test was FAIL', 'RED')
                log.logger.info("Pattern Test was FAIL!")
                return False
    # elif "GREEN"==patterntest:
    #     #if 4K, 4K capture was not support by 780E
    #     if '2160p50' in qdincode or '2160p60' in qdincode:
    #         if '2160p50' in qdoutcode or '2160p60' in qdoutcode:
    #             log.logger.info("Both In/Out are 4K")
    #             res = calculatePixel(1, 1, qd, h, v, incolor, outcolor, swcolorconfig, patterntest)
    #             if res:
    #                 tcolor.cprint('Pattern Test was PASS', 'GREEN')
    #                 log.logger.info("Pattern Test was PASS!")
    #                 return True
    #             else:
    #                 tcolor.cprint('Pattern Test was FAIL', 'RED')
    #                 log.logger.info("Pattern Test was FAIL!")
    #                 return False
    #         else:
    #             log.logger.info("In is 4K, Out not 4K")
    #             res = calculatePixel(1, 0, qd, h,v, incolor, outcolor, swcolorconfig, patterntest)
    #             if res:
    #                 tcolor.cprint('Pattern Test was PASS','GREEN')
    #                 log.logger.info("Pattern Test was PASS!")
    #                 return True
    #             else:
    #                 tcolor.cprint('Pattern Test was FAIL', 'RED')
    #                 log.logger.info("Pattern Test was FAIL!")
    #                 return False
    #     else:
    #         if '2160p50' in qdoutcode or '2160p60' in qdoutcode:
    #             log.logger.info("In not 4K, Out is 4K")
    #             res = calculatePixel(0, 1, qd, h ,v, incolor, outcolor, swcolorconfig, patterntest)
    #             if res:
    #                 tcolor.cprint('Pattern Test was PASS', 'GREEN')
    #                 log.logger.info("Pattern Test was PASS!")
    #                 return True
    #             else:
    #                 tcolor.cprint('Pattern Test was FAIL', 'RED')
    #                 log.logger.info("Pattern Test was FAIL!")
    #                 return False
    #         else:
    #             log.logger.info("Both are not 4K")
    #             res = calculatePixel(0, 0, qd, h, v, incolor, outcolor, swcolorconfig, patterntest)
    #             if res:
    #                 tcolor.cprint('Pattern Test was Pass', 'GREEN')
    #                 log.logger.info("Pattern Test was PASS!")
    #                 return True
    #             else:
    #                 tcolor.cprint('Pattern Test was FAIL', 'RED')
    #                 log.logger.info("Pattern Test was FAIL!")
    #                 return False
    # elif "BLUE" == patterntest:
    #     #if 4K, 4K capture was not support by 780E
    #     if '2160p50' in qdincode or '2160p60' in qdincode:
    #         if '2160p50' in qdoutcode or '2160p60' in qdoutcode:
    #             log.logger.info("Both In/Out are 4K")
    #             res = calculatePixel(1, 1, qd, h, v, incolor, outcolor, swcolorconfig, patterntest)
    #             if res:
    #                 tcolor.cprint('Pattern Test was PASS', 'GREEN')
    #                 log.logger.info("Pattern Test was PASS!")
    #                 return True
    #             else:
    #                 tcolor.cprint('Pattern Test was FAIL', 'RED')
    #                 log.logger.info("Pattern Test was FAIL!")
    #                 return False
    #         else:
    #             log.logger.info("In is 4K, Out not 4K")
    #             res = calculatePixel(1, 0, qd, h,v, incolor, outcolor, swcolorconfig, patterntest)
    #             if res:
    #                 tcolor.cprint('Pattern Test was PASS','GREEN')
    #                 log.logger.info("Pattern Test was PASS!")
    #                 return True
    #             else:
    #                 tcolor.cprint('Pattern Test was FAIL', 'RED')
    #                 log.logger.info("Pattern Test was FAIL!")
    #                 return False
    #     else:
    #         if '2160p50' in qdoutcode or '2160p60' in qdoutcode:
    #             log.logger.info("In not 4K, Out is 4K")
    #             res = calculatePixel(0, 1, qd, h ,v, incolor, outcolor, swcolorconfig, patterntest)
    #             if res:
    #                 tcolor.cprint('Pattern Test was PASS', 'GREEN')
    #                 log.logger.info("Pattern Test was PASS!")
    #                 return True
    #             else:
    #                 tcolor.cprint('Pattern Test was FAIL', 'RED')
    #                 log.logger.info("Pattern Test was FAIL!")
    #                 return False
    #         else:
    #             log.logger.info("Both are not 4K")
    #             res = calculatePixel(0, 0, qd, h, v, incolor, outcolor, swcolorconfig, patterntest)
    #             if res:
    #                 tcolor.cprint('Pattern Test was Pass', 'GREEN')
    #                 log.logger.info("Pattern Test was PASS!")
    #                 return True
    #             else:
    #                 tcolor.cprint('Pattern Test was FAIL', 'RED')
    #                 log.logger.info("Pattern Test was FAIL!")
    #                 return False
    # else:
    #     raise ("Unsupport aspectration was set.")

# def compareArea(outflag, h, v, desarea):
#     """
#     Copare black box area;
#     :param h: src width
#     :param v: src hight
#     :return:boolean
#     """
#     x = h
#     y = v
#     # this "if" according to 780E can not support 4K capture
#     if outflag:
#         x = round(x/2)
#         y = round(y/2)
#     srcarea = round((y*x)/4)
#     log.logger.info("The destiny is:%s" % str(desarea))
#     log.logger.info("The source  is:%s" % str(srcarea))
#     factor = ("%.2f" % float(srcarea/desarea))
#     log.logger.info("The factor is :"+ factor)
#     #compare black box
#     accpetence = ["0.97","0.98","0.99","1.00","1.01","1.02","1.03"]
#     if factor in accpetence:
#         return True
#     else:
#         return False


def getExpectColor(swcolorconfig, inflag, outflag, incolor, outcolor, colume):
    """
    Get expect color
    :param swcolorconfig:
    :param inflag: if 4k, 4k=1, non4k=0
    :param outflag: if 4k, 4k=1, non4k=0
    :param incolor:
    :param outcolor:
    :return: white color
    """
    print(inflag)
    print(outflag)
    print(incolor)
    print(outcolor)
    print(colume)
    return swcolorconfig.getExpectPixelColor(inflag,outflag,incolor,outcolor, colume)

def compColor(expcolor, pcolor):
    """
    Compare 2 Hex str color
    :param expcolor:
    :param pcolor:
    :return: boolean
    """
    expcolor = re.findall(r"0x\w+", expcolor)
    print("The expect color is %s" % expcolor)
    pcolor = re.findall(r"0x\w+", pcolor)
    print("The detect color is %s" % pcolor)
    if len(pcolor) != 3:
        return False
    for i in range(len(pcolor)):
        pcolor[i]=int(pcolor[i],16)
        expcolor[i]=int(expcolor[i],16)
    for i in range(len(pcolor)):
        if abs(pcolor[i]-expcolor[i])<=2:
            continue
        else:return False
    else:return True

def calculatePixel(inflag, outflag, qd, h, v, incolor, outcolor, swcolorconfig, patterntest):
    """
    random capture 10 points, and compare the color
    :param inflag:
    :param outflag:
    :param qd:
    :param incolor:
    :param outcolor:
    :param swcolorconfig:
    :return:
    """
    if outflag:
        h = round(h/2)
        v = round(v/2)
    print("The pattern is %s" % patterntest)
    # get expectec color;
    if "RED" == patterntest:
        print("The test pattern is %s" % patterntest)
        expcolor = getExpectColor(swcolorconfig, inflag, outflag, incolor, outcolor, 8)
    elif "GREEN" == patterntest:
        print("The test pattern is %s" % patterntest)
        expcolor = getExpectColor(swcolorconfig, inflag, outflag, incolor, outcolor, 9)
    elif "BLUE" == patterntest:
        print("The test pattern is %s" % patterntest)
        expcolor = getExpectColor(swcolorconfig, inflag, outflag, incolor, outcolor, 10)
    else:
        raise ("No this color found is datasheet!")
    # init pixel analyzer
    #qd.init_capture()
    #qd.cap_frame(100)
    #qd.init_compare_frame()
    qd.query_pixelErrCount(100)
    #get 10 random points
    for i in range(10):
        xcord = random.randint(1, h)
        ycord = random.randint(1, v)
        print("The coordinate is x: %d, y: %d " % (xcord, ycord))
        dcolor = qd.get_pixel(str(xcord), str(ycord))
        if compColor(expcolor, dcolor):
            continue
        else: return False
    return True

# def calculateBox1(inflag, outflag, qd, h1, v1, h2, v2, incolor, outcolor, swcolorconfig):
#     """
#     Calculate black/white points of the pattern.
#     :param inflag: if 4K, flag =1;
#     :param outflag: if 4K, flag =1;
#     :param qd;
#     :param h1;
#     :param v1;
#     :param h2;
#     :param v2;
#     :param incolor;
#     :param outcolor;
#     :param swcolorconfig;
#     :return: black box area;
#     """
#     x = h1
#     y = v1
#     width = h2
#     hight = v2
#     offset = 20 #pixel detect offset
#     # this "if" according to 780E can not support 4K capture
#     if outflag:
#         x = round(x/2)
#         y = round(y/2)
#         width = round(width/2)
#         hight = round(hight/2)
#     #get the expect color
#     expcolor = getExpectColor(swcolorconfig, inflag, outflag, incolor, outcolor)
#     #init pixel analyzer
#     qd.init_capture()
#     qd.cap_frame(100)
#     qd.init_compare_frame()
#     qd.query_pixelErrCount(100)
#     #get the ynorth
#     xcenter = round(x/2)
#     ycenter = int(round(y/2)-round(hight/4)+offset/2)
#     limit = ycenter-offset
#     log.logger.info("finding ynorth...")
#     while ycenter > limit:
#         pcolor = qd.get_pixel(str(xcenter), str(ycenter))
#         if compColor(expcolor, pcolor):
#             ynorth = ycenter
#             break
#         ycenter=ycenter-1
#     else:
#         ynorth = 0
#         log.logger.info("ynorth can not find!")
#     log.logger.info("ynorth is %s" % ynorth)
#     #get the ysouth
#     xcenter = round(x/2)
#     ycenter = int(round(y/2)+round(hight/4)-offset/2)
#     limit = ycenter+offset
#     log.logger.info("finding ysouth...")
#     while ycenter < limit: #10 pixel offset
#         pcolor = qd.get_pixel(str(xcenter), str(ycenter))
#         if compColor(expcolor, pcolor):
#             ysouth = ycenter
#             break
#         ycenter=ycenter+1
#     else:
#         ysouth = y
#         log.logger.info("ysouth can not find!")
#     log.logger.info("ysouth is %s" % ysouth)
#     #get the xwest
#     xcenter = int(round(x/2)-round(width/4)+offset/2)
#     ycenter = round(y/2)
#     limit = xcenter-offset
#     log.logger.info("finding xwest...")
#     while xcenter > limit:
#         pcolor = qd.get_pixel(str(xcenter), str(ycenter))
#         if compColor(expcolor, pcolor):
#             xwest = xcenter
#             break
#         xcenter=xcenter-1
#     else:
#         xwest = 0
#         log.logger.info("xwest can not find!")
#     log.logger.info("xwest is %s" % xwest)
#     #get the xeast
#     xcenter = int(round(x/2)+round(width/4)-offset/2)
#     ycenter = round(y/2)
#     limit = xcenter+offset
#     log.logger.info("finding xeast...")
#     while xcenter < limit:
#         pcolor = qd.get_pixel(str(xcenter), str(ycenter))
#         if compColor(expcolor, pcolor):
#             xeast = xcenter
#             break
#         xcenter=xcenter+1
#     else:
#         xeast = x
#         log.logger.info("xeast can not find!")
#     log.logger.info("xeast is %s" % xeast)
#     hight = ysouth - ynorth
#     width = xeast - xwest
#     return hight*width

def randSwitchPort(rand, inportdic, outportdic):
    """
    random switch the DUT and Switcher
    :param random:
    :param inportdic:
    :param outportdic:
    :return:
    """
    if 'all' == rand:
        #Random switch SUT in port
        inporttype = random.choice(list(inportdic.keys()))
        inport = inportdic[inporttype]
        #Random switch SUT out port
        outporttype = random.choice(list(outportdic.keys()))
        outport = outportdic[outporttype]
        cmd_dut = ''.join('ci' + inport + 'o' + outport)
        log.logger.info("Set the DUT port is: %s" % cmd_dut)
        #Set Switch output
        switchport = "".join(re.findall(r"\d",outporttype))
        cmd_sw = ''.join('ci'+switchport+'oall')
        #log.logger.info("Set the Switch port is: %s" % cmd_sw)
    elif 'input' == rand:
        # Random switch SUT in port, output default is first port
        inporttype = random.choice(list(inportdic.keys()))
        inport = inportdic[inporttype]
        cmd_dut = ''.join('ci' + inport + 'o' + outportdic['HDMI1'])
        log.logger.info("The DUT IN port is: %s" % inport)
        #No output switch
        log.logger.info("OUTput has no change.")
        # Set Switch output
        cmd_sw = ''
    elif 'output' == rand:
        #No switch SUT in port, input is the default
        log.logger.info("INput has no change.")
        outporttype = random.choice(list(outportdic.keys()))
        outport = outportdic[outporttype]
        cmd_dut = ''.join('ci' + inportdic['HDMI1'] + 'o' + outport)
        log.logger.info("The DUT OUT port is: %s" % outport)
        #Set Switch output
        switchport = "".join(re.findall(r"\d",outporttype))
        cmd_sw = ''.join('ci'+switchport+'oall')
        #log.logger.info("Set the Switch port is: %s" % cmd_sw)
    else:
        cmd_dut = ''.join('ci' + inportdic['HDMI1'] + 'o' + outportdic['HDMI1'])
        #Set Switch output
        switchport = "".join(re.findall(r"\d",'HDMI1'))
        cmd_sw = ''.join('ci'+switchport+'oall')
    return cmd_dut, cmd_sw, outport, outporttype, inporttype

def writeEdid(swcregconf, scalercode, edidfile, qd):
    edid = swcregconf.qdcode2edid(scalercode)
    log.logger.info("The new edid is:" + edid)
    edidobj = switchconfig.SwitchConfigOperation(edidfile, 0)
    block0 = edidobj.getEdid(edid, '0')
    block1 = edidobj.getEdid(edid, '1')
    # 4.2 write edid:
    qd.write_edid_block('0', str(block0))
    qd.write_edid_block('1', str(block1))
    # 4.3 apply edid
    qd.apply_edid()

def loadProcess():
    lineLength = 100
    delaySeconds = 0.03
    frontSymbol = '='
    frontSymbol2 = ['-', '\\', '|', '/']
    backSymbol = ' '
    lineTmpla = "{:%s<%s} {} {:<2}" % (backSymbol, lineLength)
    for j in range(lineLength):
        tmpSymbol = frontSymbol2[j % (len(frontSymbol2))]
        print("\r" + lineTmpla.format(frontSymbol * j, tmpSymbol, j), end='')
        time.sleep(delaySeconds)
    print("")

def writeTempFile(filename, resdic):
    import json
    resstr=json.dumps(resdic)
    print(resstr)
    with open(filename, 'a+') as f:
        f.write(resstr+'\n')

def main():
    """
    :return:
    """
    usage = "usage: %prog [options] args"
    parser = OptionParser(usage)
    parser.add_option("-p", dest="patternname", default="Halation", type="string", help="Set Quantum test pattern.\
                                                                                        default:halation")
    parser.add_option("-t", dest="timing", type="string", default="1080p60",help=\
                                                            "Set input timing[qdcode | all | random]\
                                                            default: 1080p60\
                                                            all: all input timing\
                                                            random: random input timing \
                                                            qdcode: the manual timing,eg,2160p30")

    parser.add_option("-s", dest="scaletiming", type="string", default="auto",help=\
                                                            "Set scale output timing.[qdcode | auto | random | manual].\
                                                            defalut:auto\
                                                            auto: all support scale timing\
                                                            random: random output timing\
                                                            manual: manual output timing\
                                                            qdcode: the manual scale timing, eg, 2160p60")
    parser.add_option("-c", dest="colorspace", type="string", default="YCbCr444",help=\
                                                            "Set Quantum colorspace.[ RGB | YCbCr444 | YCbCr422 | YCbCr420]\
                                                            defalut:RGB")
    parser.add_option("-d", dest="deepcolor", type="string", default="8",help="Set Quantum deepcolor.[8 | 10 | 12]")
    parser.add_option("-r", dest="repetitions", type="string", default="1",help="Set the test loop repetitions")
    parser.add_option("-i", dest="interval", type="string", default="1",help="Set DUT switch time interval(Uint:second)")
    parser.add_option("--hdcpout", dest="hdcpout", type="string", default="None",help="Set Quantum out HDCP.[None | 14 | 22]")
    parser.add_option("--hdcpin", dest="hdcpin", type="string", default="None",help="Set Quantum in HDCP.[None | 14 | 22]")
    parser.add_option("--hdcpdut", dest="hdcpdut", type="string", default="follow",help="Set DUT HDCP out.[None | 14 | 22 | follow]")
    parser.add_option("--outport", dest="outport", type="string", default='HDMI', \
                                                             help="Set Quantum Device output port.[HDMI | HDBT]")
    parser.add_option("--inport", dest="inport", type="string", default='HDMI', \
                                                             help="Set Quantum Device input port.[HDMI | HDBT]")
    parser.add_option("--random", dest="random", type="string",help=\
                                                            "Random Switch Input/Output ports.[ input | output | all ]")
    parser.add_option("--ar", dest="aspectratio", type="string", default ="stretch", help=\
                                                            "Set DUT AspectRatio, default is stretch .[ maintain | stretch ]")
    parser.add_option("--outcolor", dest="outcolorspace", type="string", default="RGB",help=\
                                                            "Set DUT colorspace.[ RGB | YCbCr444]\
                                                            defalut:RGB")
    parser.add_option("--patterntest", dest="patterntest", type="string", default="OFF",help=\
                                                            "Set DUT colorspace.[ RED | GREEN | BLUE]\
                                                            defalut:RGB")
    parser.add_option("-v", "--verbose", action="store_true", dest="verbose", help="Verbose out")
    options, args = parser.parse_args()
    #if not args:
        #parser.print_help()
        #exit(1)
    passnumber, failnumber, notrunnumber = executeTest(options, args)
    resdic={"passnumber":passnumber, "failnumber":failnumber, "notrunnumber":notrunnumber}
    #resdic={"passnumber":10, "failnumber":20, "notrunnumber":0}
    tmpfile = BASEDIR+"\\log\\tmp.log"
    writeTempFile(tmpfile, resdic)

if __name__=="__main__":
    main()