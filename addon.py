import bpy
import tempfile
import shlex
import shutil
import subprocess

bl_info = {
    "name": "FFmpeg Export",
    "description": "Uses external FFmpeg to encode rendered video or reencode any input video",
    "author": "Martin Zmitko",
    "version": (1),
    "blender": (4, 2),
    "location": "Render Properties",
    "support": "COMMUNITY",
    "category": "Import-Export"
}


class FF_PT_Panel(bpy.types.Panel):
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "render"
    bl_label = "FFmpeg"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        self.layout.use_property_split = True
        self.layout.use_property_decorate = False
        col = self.layout.column(align=True)
        col.prop(context.scene.ffSettings, "output")
        col = self.layout.column(align=True)
        col.prop(context.scene.ffSettings, "operation")
        col = self.layout.column(align=True)
        col.prop(context.scene.ffSettings, "preset")
        col = self.layout.column(align=True)
        if context.scene.ffSettings.operation == "render":
            col.prop(context.scene.ffSettings, "storeFrames")
            if context.scene.ffSettings.storeFrames:
                col.prop(context.scene.ffSettings, "frameDir")
        elif context.scene.ffSettings.operation == "encode":
            col.prop(context.scene.ffSettings, "frameDir")
        elif context.scene.ffSettings.operation == "reencode":
            col.prop(context.scene.ffSettings, "input")
        
        col = self.layout.column(align=True)
        col.prop(context.scene.ffSettings, "container")
        if not context.scene.ffSettings.container == "gif":
            col.prop(context.scene.ffSettings, "codec")
            col = self.layout.column(align=True)
            row = col.row(align=True)
            row.prop(context.scene.ffSettings, "colorDepth", expand=True)
            col = self.layout.column(align=True)
            col.prop(context.scene.ffSettings, "constantBitrate")
            if not context.scene.ffSettings.constantBitrate:
                col.prop(context.scene.ffSettings, "crf")
            else:
                col = self.layout.column(align=True)
                col.prop(context.scene.ffSettings, "bitrate")
                col.prop(context.scene.ffSettings, "minBitrate")
                col.prop(context.scene.ffSettings, "maxBitrate")
                col.prop(context.scene.ffSettings, "buffer")
                
                col = self.layout.column(align=True)
                col.prop(context.scene.ffSettings, "muxRate")
                col.prop(context.scene.ffSettings, "muxPacket")
        
        col = self.layout.column(align=True)
        if context.scene.ffSettings.operation == "render":
            col.operator("ffexport.render", text="Render")
        else:
            col.operator("ffexport.encode", text="Encode")
        
        col = self.layout.column(align=True)
        col.prop(context.scene.ffSettings, "path")
        col.prop(context.scene.ffSettings, "params")


class FF_OT_Encode(bpy.types.Operator):
    bl_idname = "ffexport.encode"
    bl_label = "Encode video"
    
    def getInputArgs(self, context):
        args = [context.scene.ffSettings.path, '-y']
        if context.scene.ffSettings.operation == "reencode":
            args += ['-i', context.scene.ffSettings.input]
        else:
            args += ['-r', str(context.scene.render.fps)]
            args += ['-start_number', str(context.scene.frame_start)]
            args += ['-i', context.scene.ffSettings.frameDir + '%05d.png'] 
        return args
    
    def getArgs(self, context):
        args = self.getInputArgs(context)
        args += ['-r', str(context.scene.render.fps)]
        args += ['-f', context.scene.ffSettings.container]
        if not context.scene.ffSettings.container == "gif":
            args += ['-c:v', context.scene.ffSettings.codec]
            if context.scene.ffSettings.codec in ["libx264", "libx265"]:
                args += ['-preset', context.scene.ffSettings.preset]
            elif context.scene.ffSettings.codec == "libvpx-vp9":
                presetMap = {"veryfast": "6", "medium": "3", "veryslow": "0"}
                args += ['-cpu-used', presetMap[context.scene.ffSettings.preset]]
            else:
                presetMap = {"veryfast": "8", "medium": "5", "veryslow": "2"}
                args += ['-cpu-used', presetMap[context.scene.ffSettings.preset]]
            if context.scene.ffSettings.constantBitrate:
                args += ['-b:v', str(context.scene.ffSettings.bitrate) + 'k']
                args += ['-minrate', str(context.scene.ffSettings.minBitrate) + 'k']
                args += ['-maxrate', str(context.scene.ffSettings.maxBitrate) + 'k']
                args += ['-bufsize', str(context.scene.ffSettings.buffer) + 'k']
                args += ['-muxrate', str(context.scene.ffSettings.muxRate) + 'k']
                args += ['-pkt_size', str(context.scene.ffSettings.muxPacket)]
            else:
                args += ['-crf', str(context.scene.ffSettings.crf)]
            args += ['-pix_fmt', context.scene.ffSettings.colorDepth]
        args += shlex.split(context.scene.ffSettings.params)
        args.append(context.scene.ffSettings.output)
        return args
    
    def execute(self, context):
        args = self.getArgs(context)
        pipe = subprocess.Popen(args)
        pipe.wait();
        if pipe.returncode != 0:
            raise subprocess.CalledProcessError(pipe.returncode, args)
        return {"FINISHED"}


class FF_OT_Render(bpy.types.Operator):
    bl_idname = "ffexport.render"
    bl_label = "Render animation"

    def execute(self, context):
        renderInfo = bpy.context.scene.render
        renderInfo.image_settings.file_format = 'PNG'
        
        frameDir = context.scene.ffSettings.frameDir
        if not context.scene.ffSettings.storeFrames:
            frameDir = tempfile.mkdtemp()
            
        # Render frames individually to prevent blender visually hanging
        for i in range(context.scene.frame_start, context.scene.frame_end + 1):
            context.scene.frame_set(i)
            bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
            renderInfo.filepath = frameDir + f'/{i:05d}.png'
            bpy.ops.render.render(write_still=True) 
            
        bpy.ops.ffexport.encode()

        if not context.scene.ffSettings.storeFrames:
            shutil.rmtree(frameDir)
        
        return {"FINISHED"}


containers = [
    ("matroska", "Matroska", ""),
    ("mp4", "MPEG-4", ""),
    ("webm", "WebM", ""),
    ("gif", "GIF", "")
]

def codecs(self, context):
    codecs = [
        ("libx264", "H.264", ""),
        ("libx265", "H.265", ""),
        ("libaom-av1", "AV1", ""),
        ("libvpx-vp9", "VP9", "")
    ]
    if self.container == "webm":
        return codecs[2:]
    elif self.container == "mp4":
        return codecs[:3]
    else:
        return codecs

def colorDepths(self, context):
    depths = [
        ("yuv420p", "8", ""),
        ("yuv420p10le", "10", ""),
        ("yuv420p12le", "12", "")
    ]
    if self.codec == "libaom-av1":
        return depths[:1]
    elif self.codec == "libx264":
        return depths[:2]
    else:
        return depths

class FF_Settings(bpy.types.PropertyGroup):
    operation: bpy.props.EnumProperty(
        name="Operation",
        description="Type of operation to execute",
        items=[
            ("render", "Render", "Render the current scene and encode with custom parameters"),
            ("encode", "Encode frames", "Encode an (already rendered) series of frames"),
            ("reencode", "Reencode video", "Reencodes an input video with custom parameters")
        ]
    )
    
    container: bpy.props.EnumProperty(
        name="Container",
        description="The output video container",
        items=containers
    )
    
    preset: bpy.props.EnumProperty(
        name="Encoding Speed",
        description="Controls the encoding speed. The tradeoff for faster speed is larger file size",
        items=[
            ("veryfast", "Fast", ""),
            ("medium", "Balanced", ""),
            ("veryslow", "Slow", "")
        ],
        default="medium"
    )
    
    path: bpy.props.StringProperty(name="FFmpeg Path", subtype="FILE_PATH", description="The path to the ffmpeg binary", default="ffmpeg")
    input: bpy.props.StringProperty(name="Input File", subtype="FILE_PATH", description="The input file with extension", default="myFile.mkv")
    output: bpy.props.StringProperty(name="Output File", subtype="FILE_PATH", description="The output file with extension", default="myFile.mkv")
    frameDir: bpy.props.StringProperty(name="Frames Folder", subtype="DIR_PATH", description="The path to the folder where frames are stored", default="./myFrames")
    params: bpy.props.StringProperty(name="Additional Parameters", description="Additional FFMPEG parameters")
    storeFrames: bpy.props.BoolProperty(name="Store Frames", description="Keep individual frames", default=False)
    
    codec: bpy.props.EnumProperty(name="Codec", description="The output video codec", items=codecs)
    colorDepth: bpy.props.EnumProperty(name="Color Depth", description="The output video color depth", items=colorDepths)
    
    constantBitrate: bpy.props.BoolProperty(name="Constant Bitrate", description="Use constant bitrate", default=False)
    crf: bpy.props.IntProperty(name="Constant Rate Factor", description="CRF setting", default=23, min=0, max=51)
    bitrate: bpy.props.IntProperty(name="Bitrate", description="Video bitrate (kbit/s)", default=6000, min=0)
    minBitrate: bpy.props.IntProperty(name="Minimum", description="Minimal bitrate (kbit/s)", default=0, min=0)
    maxBitrate: bpy.props.IntProperty(name="Maximum", description="Maximal bitrate (kbit/s)", default=9000, min=0)
    buffer: bpy.props.IntProperty(name="Buffer", default=1792, description="Buffer size  (kb)", min=0)
    muxRate: bpy.props.IntProperty(name="Mux Rate", description="Video mux rate (kbit/s)", default=10080, min=0)
    muxPacket: bpy.props.IntProperty(name="Mux Packet Size", description="Video mux packet size (byte)", default=2048, min=0)
    keyframeInterval: bpy.props.IntProperty(name="Keyframe Interval", description="Distance between key frames", default=18, min=0, max=50)


def register():
    bpy.utils.register_class(FF_PT_Panel)
    bpy.utils.register_class(FF_OT_Render)
    bpy.utils.register_class(FF_OT_Encode)
    bpy.utils.register_class(FF_Settings)
    bpy.types.Scene.ffSettings = bpy.props.PointerProperty(type=FF_Settings)

def unregister():
    bpy.utils.unregister_class(FF_PT_Panel)
    bpy.utils.unregister_class(FF_OT_Render)
    bpy.utils.unregister_class(FF_OT_Encode)
    bpy.utils.unregister_class(FF_Settings)
    del bpy.types.Scene.ffSettings
    
if __name__ == "__main__" :
    register()       