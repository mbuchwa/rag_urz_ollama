import Home from "./components/Home";
import background from "/imgs/background.jpg";

export default function App() {
  return (
    <div
      className="min-h-screen flex flex-col bg-cover bg-center"
      style={{ backgroundImage: `url(${background})` }}
    >
      <Home />
    </div>
  );
}