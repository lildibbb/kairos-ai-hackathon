import { Composition, Folder } from "remotion";
import { KairosPromo } from "./KairosPromo";
import { Turn } from "./scenes/Turn";
import { Reveal } from "./scenes/Reveal";
import { Demo } from "./scenes/Demo";
import { Impact } from "./scenes/Impact";
import { Close } from "./scenes/Close";

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="KairosPromo"
        component={KairosPromo}
        durationInFrames={4500}
        fps={30}
        width={1920}
        height={1080}
        defaultProps={{ rootCauseSeconds: 12, showCaptions: true, musicVolume: 0.6 }}
      />
      <Folder name="Scenes">
        <Composition id="Turn" component={Turn} durationInFrames={300} fps={30} width={1920} height={1080} />
        <Composition id="Reveal" component={Reveal} durationInFrames={750} fps={30} width={1920} height={1080} />
        <Composition id="Demo" component={Demo} durationInFrames={2100} fps={30} width={1920} height={1080} defaultProps={{ rootCauseSeconds: 12 }} />
        <Composition id="Impact" component={Impact} durationInFrames={600} fps={30} width={1920} height={1080} />
        <Composition id="Close" component={Close} durationInFrames={750} fps={30} width={1920} height={1080} />
      </Folder>
    </>
  );
};
