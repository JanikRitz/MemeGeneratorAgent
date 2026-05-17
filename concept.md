
# Meme Generator

Agent + Skill + Scripts to generate still and animated memes

Requirements

-  The agent/skills should be able to
- put text on top of or around the media
- use a certain segment of video
- use two images/videos side by side
- use two clips one after the other
- add more than one text (space/time)
- format text on word level, italicised/bold, colour, ... 

## Stack

- Windows
- Python (uv?)
- FFMPEG
- VS Code with agents (agent.md + skill.md + scripts)

## Architecture

```text
[ VS Code / Agent Layer ]  --> (Interprets your prompt: "Make a side-by-side meme...")
         |
         v
[ Python Scripts / Skills ] --> (Executes specialized functions: trim, stack, overlay)
         |
         v
[ FFmpeg / Pillow Engines ] --> (Processes media streams directly from your NAS)
```

The Formatting Trick: Word-Level Text Styling

The Secret: FFmpeg’s drawtext filter is terrible at styling individual words (e.g., making one word bold and red mid-sentence). The best approach is to use Pillow (PIL) in Python to render the text onto a transparent PNG canvas with your exact formatting, and then use FFmpeg/MoviePy to overlay that transparent image onto the video.

Blueprint for the Skills Script [Meme Engine](.github/scripts/MemeEngine.py)

Modular function we will need:

- trim_video(input_path, start_time, end_time, output_path): Cuts a specific segment using MoviePy's subclip.
- stack_media(path1, path2, orientation='horizontal'): Uses MoviePy’s clips_array to put two videos/images side-by-side or top-and-bottom.
- concatenate_clips(clip_list): Strings multiple clips together sequentially.
- generate_text_overlay(text_data, video_width, video_height): A function using Pillow that parses a mini-syntax (like This is [color:red,weight:bold]epic[/color]) to generate a transparent text overlay.
- apply_overlay(video_path, overlay_image_path, timestamp, position): Blits the text canvas onto the video at a specific time and screen coordinate.