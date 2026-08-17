import { useNavigate } from "react-router-dom";

import { useAuth } from "../hooks/useAuth";

export function Header() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  function handleLogout() {
    logout();
    navigate("/login");
  }

  return (
    <header className="header">
      <span>
        {user ? `${user.first_name} ${user.last_name}` : ""}
      </span>
      <button onClick={handleLogout}>Logout</button>
    </header>
  );
}
