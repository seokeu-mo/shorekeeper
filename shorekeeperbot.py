import asyncio
import discord
import yt_dlp as youtube_dl

from discord.ext import commands
from discord import app_commands
from yt_token import Token

intents = discord.Intents.default()
intents.message_content = True

# YouTube DL 설정 유지
youtube_dl.utils.bug_reports_message = lambda *args, **kwargs: ''
ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0'
}
ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}
ytdl = youtube_dl.YoutubeDL(ytdl_format_options)

# Embed 템플릿 함수 (유지)
def make_embed(title=None, description=None, color=0x0086ff, fields=None,
               footer="Shorekeeper version-1.0.0(Beta)",
               thumbnail="https://drive.google.com/u/0/drive-viewer/AKGpihbEQX5qzvbgm_tOdOFAMWoCd86GNvF_jjfco-jtwjTHgQQwsmEIczv_Ov0DAXc86SumDVnxW5tjurRI3cb23T4FA4qk8UiZENo=s1600-rw-v1",
               author=("Shorekeeper", "https://drive.google.com/u/0/drive-viewer/AKGpihbEQX5qzvbgm_tOdOFAMWoCd86GNvF_jjfco-jtwjTHgQQwsmEIczv_Ov0DAXc86SumDVnxW5tjurRI3cb23T4FA4qk8UiZENo=s1600-rw-v1"),
               image=False):
    embed = discord.Embed(title=title, description=description, color=color)
    if fields:
        for name, value, inline in fields:
            embed.add_field(name=name, value=value, inline=inline)
    if footer:
        embed.set_footer(text=footer)
    if thumbnail:
        embed.set_thumbnail(url=thumbnail)
    if author:
        embed.set_author(name=author[0], icon_url=author[1])
    if image:
        embed.set_image(url="https://drive.google.com/u/0/drive-viewer/AKGpihbEQX5qzvbgm_tOdOFAMWoCd86GNvF_jjfco-jtwjTHgQQwsmEIczv_Ov0DAXc86SumDVnxW5tjurRI3cb23T4FA4qk8UiZENo=s1600-rw-v1")
    return embed

# 음악 재생용 YTDLSource
class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False, volume = 0.5):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))
        if 'entries' in data:
            data = data['entries'][0]
        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data, volume=volume)

# 봇 클래스 설정
class MusicClient(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.all())
        self.tree = app_commands.CommandTree(self)
        self.queue = []
        self.current_player = None
        self.max_queue_size = 10
        self.playing_interaction = None
        self.inactive_timer = None
        self.looping = False
        self.loop_message_sent = False
        self.volume = 0.5

    async def setup_hook(self):
        self.tree.copy_global_to(guild=discord.Object(id=960900387483816017))
        await self.tree.sync(guild=discord.Object(id=960900387483816017))

    async def play_next(self):
        if self.looping and self.current_player:
            title = self.current_player.title
            player = await YTDLSource.from_url(self.current_player.url, loop=self.loop, stream=True, volume=self.volume)
            vc = self.playing_interaction.guild.voice_client
            vc.play(player, after=lambda e: asyncio.run_coroutine_threadsafe(self.play_next(), self.loop))
            self.current_player = player
            self.current_player.title = title
            if not self.loop_message_sent:
                embed = make_embed(title="🔁 반복 재생", description=f"{self.current_player.title} 반복 재생 중입니다!")
                await self.playing_interaction.channel.send(embed=embed)
                self.loop_message_sent = True
            self.reset_inactive_timer(vc, self.playing_interaction)
            self.loop_message_sent = False
            return

        self.loop_message_sent = False

        if self.queue:
            url, title, interaction = self.queue.pop(0)
            player = await YTDLSource.from_url(url, loop=self.loop, stream=True, volume=self.volume)
            vc = interaction.guild.voice_client
            vc.play(player, after=lambda e: asyncio.run_coroutine_threadsafe(self.play_next(), self.loop))
            self.current_player = player
            self.playing_interaction = interaction
            embed = make_embed(title="🎶 다음 곡 재생", description=f"{player.title} 재생 중입니다!")
            await interaction.channel.send(embed=embed)
            self.reset_inactive_timer(vc, interaction)

    def reset_inactive_timer(self, vc, interaction):
        if self.inactive_timer and not self.inactive_timer.done():
            self.inactive_timer.cancel()
        self.inactive_timer = self.loop.create_task(self.inactivity_check(vc, interaction))

    async def inactivity_check(self, vc, interaction):
        await asyncio.sleep(300)
        if not vc.is_playing() and not self.queue:
            await vc.disconnect()
            embed = make_embed(title="🕒 자동 종료", description="5분간 활동이 없어 음성 채널에서 퇴장합니다.")
            await interaction.channel.send(embed=embed)


client = MusicClient()

@client.event
async def on_ready():
    print(f"Logged in as {client.user} (ID: {client.user.id})")
    await client.change_presence(status=discord.Status.online,
                                 activity=discord.Game("활성화"))

@client.tree.command(name="help", description="Shorekeeper 봇 명령어를 보여줍니다.")
async def help(interation: discord.Interaction):
    await interation.response.defer()
    embed = make_embed(
        title="✅ 도움말",
        description="현재 적용 중인 Shorekeeper Bot의 명령어입니다.",
        fields=[("✅ /help", "Shorekeeper 봇 명령어를 보여줍니다.", False),
                ("✅ /info", "Shorekeeper 봇 정보를 보여줍니다.", False),
                ("✅ /play [url or title]", "유튜브 링크 혹은 검색을 통해 음악을 재생합니다.", False),
                ("✅ /now", "현재 재생 중인 음악과 반복 상태를 확인합니다.", False),
                ("✅ /clear", "대기열을 비웁니다.", False),
                ("✅ /loop", "현재 곡을 반복 재생합니다.", False),
                ("✅ /skip", "대기열의 다음 노래로 건너뜁니다.", False),
                ("✅ /stop", "재생을 중지하고 음성 채널에서 나갑니다.", False),
                ("✅ /queue", "현재 대기열을 표시합니다.", False),
                ("✅ /pause", "현재 재생중인 음악을 일시정지합니다.", False),
                ("✅ /resume", "일시정지된 음악을 다시 재생합니다.", False),
                ("✅ /volume [0~100]", "음악 재생 볼륨을 조절합니다 (0~100)", False),
                ("✅ /remove [num]", "대기열에서 특정 곡을 삭제합니다.", False)]
    )
    await interation.followup.send(embed=embed)
@client.tree.command(name="info", description="Shorekeeper 봇 정보를 보여줍니다.")
async def info(interaction: discord.Interaction):
    await interaction.response.defer()
    embed = make_embed(
        title="✅ 정보",
        description="현재 적용 중인 Shorekeeper Bot의 정보입니다.",
        fields=[("✅ 이름", "Shorekeeper Bot", False),
                ("✅ Version", "1.0.0(Beta)", False),
                ("✅ 제작자", "Seokeumo", True),
                ("✅ 문의", "E-mail: seokeumo0707@gmail.com", True)],
        thumbnail=None,
        image=True
    )
    await interaction.followup.send(embed=embed)

@client.tree.command(name="play", description="유튜브 링크로 음악을 재생합니다.")
@app_commands.describe(url="YouTube URL 또는 검색어")
async def play(interaction: discord.Interaction, url: str):
    await interaction.response.defer()
    try:
        if not interaction.user.voice or not interaction.user.voice.channel:
            embed = make_embed(title="❌ 오류", description="음성 채널에 먼저 입장해주세요.")
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        if not interaction.guild.voice_client:
            await interaction.user.voice.channel.connect()

        player = await YTDLSource.from_url(url, loop=client.loop, stream=True)
        vc = interaction.guild.voice_client

        if not vc.is_playing():
            client.queue.append((url, player.title, interaction))
            await client.play_next()
            embed = make_embed(title="✅ 재생 시작", description=f"{player.title} 재생을 시작합니다!")
        else:
            client.queue.append((url, player.title, interaction))
            embed = make_embed(title="📥 대기열 추가", description=f"{player.title} 대기열에 추가되었습니다. 현재 대기열: {len(client.queue)}곡")
        await interaction.followup.send(embed=embed)
    except Exception as e:
        embed = make_embed(title="❌ 오류", description=f"ERROR 404\n{e}")
        await interaction.followup.send(embed=embed)

@client.tree.command(name="now", description="현재 재생 중인 음악과 반복 상태를 확인합니다.")
async def now(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if not vc or not client.current_player:
        embed = make_embed(title="ℹ️ 정보 없음", description="현재 재생 중인 음악이 없습니다.")
    else:
        looping_status = "🔁 반복 재생 중" if client.looping else "▶️ 일반 재생 중"
        embed = make_embed(title="🎧 현재 음악 정보", 
                           fields=[("✅ Now playing:", f"{client.current_player.title}", False),
                                   ("✅ 반복 상태:", f"{looping_status}", False),
                                   ("✅ 현재 볼륨:", f"{client.volume*100}%", False)],)
    await interaction.response.send_message(embed=embed)

@client.tree.command(name="clear", description="대기열을 비웁니다.")
async def clear(interaction: discord.Interaction):
    client.queue.clear()
    embed = make_embed(title="🧹 대기열 비움", description="대기열이 모두 삭제되었습니다.")
    await interaction.response.send_message(embed=embed)

@client.tree.command(name="loop", description="현재 곡을 반복 재생합니다.")
async def loop(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if not vc or not vc.is_playing():
        embed = make_embed(title="❌ 반복 재생 불가", description="반복 재생을 시작하려면 현재 재생 중인 음악이 있어야 합니다.")
        await interaction.response.send_message(embed=embed)
        return

    client.looping = not client.looping
    status = "활성화됨 🔁" if client.looping else "비활성화됨 ❌"
    embed = make_embed(title="🔁 반복 재생 토글", description=f"반복 재생이 {status}.")
    await interaction.response.send_message(embed=embed)


@client.tree.command(name="skip", description="현재 곡을 건너뜁니다.")
async def skip(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and vc.is_playing():
        vc.stop()
        embed = make_embed(title="⏭️ 스킵", description="다음 곡으로 넘어갑니다.")
    else:
        embed = make_embed(title="❌ 스킵 실패", description="현재 재생 중인 곡이 없습니다.")
    await interaction.response.send_message(embed=embed)

@client.tree.command(name="stop", description="음악을 정지하고 음성 채널에서 나갑니다.")
async def stop(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc:
        vc.stop()
        await vc.disconnect()
        client.queue.clear()
        client.current_player = None
        embed = make_embed(title="🛑 정지", description="음악을 정지하고 음성 채널에서 나갔습니다.")
    else:
        embed = make_embed(title="❌ 정지 실패", description="봇이 음성 채널에 없습니다.")
    await interaction.response.send_message(embed=embed)

@client.tree.command(name="queue", description="현재 대기열을 표시합니다.")
async def queue(interaction: discord.Interaction):
    if not client.queue:
        embed = make_embed(title="✅ 대기열", description="현재 대기열이 비어있습니다.")
    else:
        queue_desc = "\n".join(f"{i+1}. {title}" for i, (_, title, _) in enumerate(client.queue))
        embed = make_embed(title="✅ 대기열", description=queue_desc)
    await interaction.response.send_message(embed=embed)

@client.tree.command(name="pause", description="현재 재생 중인 음악을 일시정지합니다.")
async def pause(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and vc.is_playing():
        vc.pause()
        embed = make_embed(title="⏸️ 일시정지", description="음악이 일시정지되었습니다.")
    else:
        embed = make_embed(title="❌ 실패", description="일시정지할 음악이 없습니다.")
    await interaction.response.send_message(embed=embed)

@client.tree.command(name="resume", description="일시정지된 음악을 다시 재생합니다.")
async def resume(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and vc.is_paused():
        vc.resume()
        embed = make_embed(title="▶️ 재생", description="음악을 다시 재생합니다.")
    else:
        embed = make_embed(title="❌ 실패", description="재생할 음악이 없습니다.")
    await interaction.response.send_message(embed=embed)

@client.tree.command(name="volume", description="음악 재생 볼륨을 조절합니다 (0~100)")
@app_commands.describe(value="볼륨 값")
async def volume(interaction: discord.Interaction, value: int):
    if value < 0 or value > 100:
        embed = make_embed(title="❌ 실패", description="0부터 100 사이의 숫자를 입력해주세요.")
    else:
        client.volume = value / 100
        interaction.guild.voice_client.source.volume = client.volume
        embed = make_embed(title="🔊 볼륨 조절", description=f"볼륨이 {value}%로 설정되었습니다.")
    await interaction.response.send_message(embed=embed)

@client.tree.command(name="remove", description="대기열에서 특정 곡을 삭제합니다.")
@app_commands.describe(index="삭제할 곡 번호 (1부터 시작)")
async def remove(interaction: discord.Interaction, index: int):
    if not 1 <= index <= len(client.queue):
        embed = make_embed(title="❌ 삭제 실패", description=f"올바른 번호를 입력해주세요. (1~{len(client.queue)})")
    else:
        _, title, _ = client.queue.pop(index - 1)
        embed = make_embed(title="🗑️ 삭제 완료", description=f"{index}번 곡 \"{title}\" 이(가) 삭제되었습니다.")
    await interaction.response.send_message(embed=embed)

client.run(Token)
