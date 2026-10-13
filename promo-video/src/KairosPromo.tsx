import type React from "react";
import { AbsoluteFill, Sequence, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { Audio } from "@remotion/media";
import { Grain } from "./components/Backdrop";
import { Captions } from "./components/Type";
import { Turn } from "./scenes/Turn";
import { Reveal } from "./scenes/Reveal";
import { Demo } from "./scenes/Demo";
import { Impact } from "./scenes/Impact";
import { Close } from "./scenes/Close";
import { sec } from "./motion";
import timeline from "./timeline.json";
import durations from "./vo-durations.json";

export type PromoProps = {
  /** Measured time-to-root-cause from a real run. Replace before sharing. */
  rootCauseSeconds: number;
  showCaptions: boolean;
  musicVolume: number;
};

const SFX_LEN: Record<string, number> = { low_note: 4.5, chime_final: 5, impact_big: 4, shimmer: 3, chime: 3, hit: 3, ping: 3 };

export const KairosPromo: React.FC<PromoProps> = ({ rootCauseSeconds, showCaptions, musicVolume }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;
  return (
    <AbsoluteFill style={{ background: "#000" }}>
      <Sequence name="Act 2 · The turn" from={sec(0)} durationInFrames={sec(10)} premountFor={fps}>
        <Turn />
      </Sequence>
      <Sequence name="Act 3 · Meet Kairos" from={sec(10)} durationInFrames={sec(25)} premountFor={fps}>
        <Reveal />
      </Sequence>
      <Sequence name="Act 4 · The demo" from={sec(35)} durationInFrames={sec(70)} premountFor={fps}>
        <Demo rootCauseSeconds={rootCauseSeconds} />
      </Sequence>
      <Sequence name="Act 5 · The impact" from={sec(105)} durationInFrames={sec(20)} premountFor={fps}>
        <Impact />
      </Sequence>
      <Sequence name="Act 6 · Next + close" from={sec(125)} durationInFrames={sec(25)} premountFor={fps}>
        <Close />
      </Sequence>

      <Grain />
      {showCaptions && <Captions t={t} />}

      <Audio name="Music" src={staticFile("music.wav")} volume={musicVolume} />
      {Object.entries(timeline.vo).map(([id, at]) => (
        <Sequence key={id} name={`VO ${id}`} from={sec(at)} durationInFrames={Math.ceil(((durations as Record<string, number>)[id] + 0.3) * fps)} premountFor={fps}>
          <Audio src={staticFile(`vo/${id}.wav`)} volume={1} />
        </Sequence>
      ))}
      {timeline.sfx.map(([name, at, vol], i) => (
        <Sequence key={`${name}-${i}`} name={`SFX ${name}`} from={sec(at as number)} durationInFrames={sec(SFX_LEN[name as string] ?? 2.5)} premountFor={fps}>
          <Audio src={staticFile(`sfx/${name}.wav`)} volume={vol as number} />
        </Sequence>
      ))}
    </AbsoluteFill>
  );
};
